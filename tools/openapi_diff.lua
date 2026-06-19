-- =============================================================================
-- openapi_diff.lua  -  OpenAPI Spec Diff Tool
-- =============================================================================
--
-- "Every API is a living document. Like a river, it changes. Unlike a river,
--  we should probably track those changes."
--    -  Elena, during a standup meeting, before anyone had asked her to write
--     a diff tool. She wrote it anyway. She had already started. It was too
--     late to stop her. The team did not try to stop her. We have learned.
--
-- This tool compares two OpenAPI specification files and reports the
-- differences between them, classified by severity:
--   - breaking: removed paths, removed methods, removed response fields, narrowed enums
--   - non_breaking: added optional fields, added endpoints
--   - informational: changed descriptions, line count changes, emoji deltas
--
-- Usage:
--   lua tools/openapi_diff.lua --left old.yaml --right new.yaml [--format text|json]
--   lua tools/openapi_diff.lua --local v3.yaml --remote https://...
--   lua tools/openapi_diff.lua --self v3.yaml  # existential mode

local DIFF_COLOR_ADD = "\27[32m"
local DIFF_COLOR_REMOVE = "\27[31m"
local DIFF_COLOR_CHANGE = "\27[33m"
local DIFF_COLOR_META = "\27[36m"
local DIFF_COLOR_RESET = "\27[0m"
local RED = "\27[31m"
local YELLOW = "\27[33m"
local RESET = "\27[0m"

-- =============================================================================
-- YAML Keyword Parser
-- =============================================================================
-- Elena's YAML parser works by counting colons. Enhanced to extract
-- response fields, enum values, required/optional status for severity
-- classification. She is still aware this is not how YAML works.
-- She still does not care.

local function parse_yaml_keywords(filepath)
  local file, err = io.open(filepath, "r")
  if not file then
    print(RED .. "[Diff] Cannot open file: " .. filepath .. RESET)
    print(RED .. "[Diff] Elena suggests checking the file path." .. RESET)
    os.exit(1)
  end

  local content = file:read("*all")
  file:close()

  local paths = {}
  local schemas = {}
  local emoji_count = 0
  local current_path = nil
  local current_method = nil
  local in_paths = false
  local in_schemas = false
  local in_response_schema = false
  local in_schema_properties = false
  local current_schema_name = nil
  local current_field = nil

  local methods = { get=true, post=true, put=true, delete=true, patch=true }

  for line in content:gmatch("[^\r\n]+") do
    local indent = line:match("^(%s*)")
    local indent_level = indent and #indent or 0

    local key, value = line:match("^%s*([%w_%-/]+):%s*(.*)")
    if not key then
      key, value = line:match("^%s*(%S+):%s*(.*)")
    end
    local list_value = nil
    if not key then
      list_value = line:match("^%s*%- (%S+.*)")
      if list_value then key = "-" end
    end
    if key then
      value = value or ""

      if indent_level == 0 and key == "paths" then
        in_paths = true; in_schemas = false
      elseif indent_level == 0 and key == "components" then
        in_schemas = true; in_paths = false
      elseif indent_level == 0 and key ~= "paths" and key ~= "components" then
        -- ignore
      end

      if in_paths then
        if indent_level == 2 and key:match("^/") then
          current_path = key
          in_response_schema = false
          if not paths[current_path] then
            paths[current_path] = { methods = {} }
          end
        elseif indent_level == 4 and methods[key] then
          current_method = key
          in_response_schema = false
          if current_path and not paths[current_path].methods[key] then
            paths[current_path].methods[key] = {
              description = "",
              responses = {},
              response_fields = {},
              enums = {}
            }
          end
        elseif indent_level == 6 and key == "operationId" and current_path and current_method then
          paths[current_path].methods[current_method].operationId = value
        elseif indent_level == 6 and key == "description" and current_path and current_method then
          paths[current_path].methods[current_method].description = value
        elseif indent_level == 8 and key == "responses" then
          in_response_schema = false
        elseif indent_level == 10 and key:match("^%d%d%d$") and current_path and current_method then
          paths[current_path].methods[current_method].responses[key] = true
          in_response_schema = false
        elseif indent_level == 16 and key == "properties" and in_response_schema then
          -- properties inside response schema
        elseif indent_level == 18 and current_path and current_method and in_response_schema then
          current_field = key
          table.insert(paths[current_path].methods[current_method].response_fields, key)
        elseif indent_level == 20 and key == "enum" and current_path and current_method and current_field then
          in_response_schema = true
          paths[current_path].methods[current_method].enums[current_field] = {}
        elseif indent_level == 22 and current_path and current_method and current_field and in_response_schema then
          local enum_val = list_value or value:match("^%s*%- (%S+)")
          if enum_val and paths[current_path].methods[current_method].enums[current_field] then
            table.insert(paths[current_path].methods[current_method].enums[current_field], enum_val)
          end
        end

        if indent_level == 14 and key == "schema" and current_path and current_method then
          in_response_schema = true
        elseif indent_level == 6 and key == "responses" and current_path and current_method then
          in_response_schema = false
        end
      end

      if in_schemas then
        if indent_level == 4 and not methods[key] and key ~= "schemas" and key ~= "type" and key ~= "properties" and key ~= "required" then
          current_schema_name = key
          in_schema_properties = false
          if not schemas[current_schema_name] then
            schemas[current_schema_name] = { properties = {}, required = {}, enums = {} }
          end
        elseif indent_level == 6 and key == "properties" then
          in_schema_properties = true
        elseif indent_level == 6 and key == "required" then
          in_schema_properties = false
        elseif indent_level == 8 and in_schema_properties and current_schema_name then
          current_field = key
          table.insert(schemas[current_schema_name].properties, key)
        elseif indent_level == 10 and key == "enum" and current_schema_name and current_field then
          schemas[current_schema_name].enums[current_field] = {}
        elseif indent_level == 10 and current_schema_name and current_field then
          local enum_val = list_value or value:match("^%s*%- (%S+)")
          if enum_val and schemas[current_schema_name].enums[current_field] then
            table.insert(schemas[current_schema_name].enums[current_field], enum_val)
          end
        elseif indent_level == 8 and key == "required" then
          in_schema_properties = false
        end
      end

      for _ in value:gmatch("[\226-\229][\128-\191][\128-\191]") do
        emoji_count = emoji_count + 1
      end
    end
  end

  -- parse required fields from schema
  local f2 = io.open(filepath, "r")
  local c2 = f2:read("*all")
  f2:close()
  local in_req = false
  local cur_schema = nil
  for line in c2:gmatch("[^\r\n]+") do
    local indent = line:match("^(%s*)")
    local il = indent and #indent or 0
    local k, v = line:match("^%s*([%w_%-]+):%s*(.*)")
    if k then
      if il == 4 and not methods[k] and k ~= "schemas" and k ~= "type" and k ~= "properties" and k ~= "required" and schemas[k] then
        cur_schema = k
        in_req = false
      elseif il == 6 and k == "required" then
        in_req = true
      elseif il == 6 and k ~= "required" then
        in_req = false
      elseif il == 8 and in_req and cur_schema and v then
        local req_field = v:match("^%s*%- (.+)")
        if req_field then
          table.insert(schemas[cur_schema].required, req_field)
        end
      end
    end
  end

  return {
    paths = paths,
    schemas = schemas,
    emoji_count = emoji_count,
    line_count = select(2, c2:gsub("\n", "\n")) + 1
  }
end

-- =============================================================================
-- Severity Classification
-- =============================================================================

local function classify_changes(left, right)
  local changes = {
    breaking = {},
    non_breaking = {},
    informational = {}
  }

  local left_paths = {}
  local right_paths = {}

  for path, data in pairs(left.paths) do
    left_paths[path] = data
  end
  for path, data in pairs(right.paths) do
    right_paths[path] = data
  end

  for path, data in pairs(right_paths) do
    if not left_paths[path] then
      table.insert(changes.non_breaking, {
        type = "added_endpoint",
        path = path,
        detail = "New endpoint added"
      })
    end
  end

  for path, data in pairs(left_paths) do
    if not right_paths[path] then
      table.insert(changes.breaking, {
        type = "removed_path",
        path = path,
        detail = "Path removed: " .. path
      })
    end
  end

  for path, rdata in pairs(right_paths) do
    if left_paths[path] then
      local ldata = left_paths[path]

      for method, _ in pairs(rdata.methods) do
        if not ldata.methods[method] then
          table.insert(changes.non_breaking, {
            type = "added_method",
            path = path,
            method = method,
            detail = method:upper() .. " added to " .. path
          })
        end
      end

      for method, _ in pairs(ldata.methods) do
        if not rdata.methods[method] then
          table.insert(changes.breaking, {
            type = "removed_method",
            path = path,
            method = method,
            detail = method:upper() .. " removed from " .. path
          })
        end
      end

      for method, mdata in pairs(ldata.methods) do
        if rdata.methods[method] then
          local rmethod = rdata.methods[method]

          for _, req_field in ipairs(mdata.response_fields) do
            local found = false
            for _, rf in ipairs(rmethod.response_fields) do
              if rf == req_field then found = true; break end
            end
            if not found then
              table.insert(changes.breaking, {
                type = "removed_response_field",
                path = path,
                method = method,
                field = req_field,
                detail = "Field '" .. req_field .. "' removed from " .. method:upper() .. " " .. path
              })
            end
          end

          for _, new_field in ipairs(rmethod.response_fields) do
            local found = false
            for _, lf in ipairs(mdata.response_fields) do
              if lf == new_field then found = true; break end
            end
            if not found then
              table.insert(changes.non_breaking, {
                type = "added_response_field",
                path = path,
                method = method,
                field = new_field,
                detail = "Field '" .. new_field .. "' added to " .. method:upper() .. " " .. path
              })
            end
          end

          for field, lvals in pairs(mdata.enums) do
            if rmethod.enums[field] then
              local rvals = rmethod.enums[field]
              local rset = {}
              for _, v in ipairs(rvals) do rset[v] = true end
              for _, lv in ipairs(lvals) do
                if not rset[lv] then
                  table.insert(changes.breaking, {
                    type = "narrowed_enum",
                    path = path,
                    method = method,
                    field = field,
                    value = lv,
                    detail = "Enum value '" .. lv .. "' removed from " .. field .. " in " .. method:upper() .. " " .. path
                  })
                end
              end
            end
          end

          if mdata.description ~= rmethod.description and mdata.description ~= "" and rmethod.description ~= "" then
            table.insert(changes.informational, {
              type = "description_changed",
              path = path,
              method = method,
              detail = "Description changed in " .. method:upper() .. " " .. path
            })
          end
        end
      end
    end
  end

  for schema_name, sdata in pairs(left.schemas) do
    if not right.schemas[schema_name] then
      table.insert(changes.breaking, {
        type = "removed_schema",
        schema = schema_name,
        detail = "Schema '" .. schema_name .. "' removed"
      })
    end
  end

  for schema_name, sdata in pairs(right.schemas) do
    if not left.schemas[schema_name] then
      table.insert(changes.non_breaking, {
        type = "added_schema",
        schema = schema_name,
        detail = "Schema '" .. schema_name .. "' added"
      })
    end
  end

  for schema_name, sdata in pairs(left.schemas) do
    if right.schemas[schema_name] then
      local rschema = right.schemas[schema_name]

      for _, prop in ipairs(sdata.properties) do
        local found = false
        for _, rp in ipairs(rschema.properties) do
          if rp == prop then found = true; break end
        end
        if not found then
          table.insert(changes.breaking, {
            type = "removed_schema_field",
            schema = schema_name,
            field = prop,
            detail = "Field '" .. prop .. "' removed from schema '" .. schema_name .. "'"
          })
        end
      end

      for _, prop in ipairs(rschema.properties) do
        local found = false
        for _, lp in ipairs(sdata.properties) do
          if lp == prop then found = true; break end
        end
        if not found then
          table.insert(changes.non_breaking, {
            type = "added_schema_field",
            schema = schema_name,
            field = prop,
            detail = "Field '" .. prop .. "' added to schema '" .. schema_name .. "'"
          })
        end
      end

      for field, lvals in pairs(sdata.enums) do
        if rschema.enums[field] then
          local rvals = rschema.enums[field]
          local rset = {}
          for _, v in ipairs(rvals) do rset[v] = true end
          for _, lv in ipairs(lvals) do
            if not rset[lv] then
              table.insert(changes.breaking, {
                type = "narrowed_enum",
                schema = schema_name,
                field = field,
                value = lv,
                detail = "Enum value '" .. lv .. "' removed from " .. field .. " in schema '" .. schema_name .. "'"
              })
            end
          end
        end
      end
    end
  end

  if left.emoji_count ~= right.emoji_count then
    local delta = right.emoji_count - left.emoji_count
    table.insert(changes.informational, {
      type = "emoji_change",
      detail = "Emoji count changed by " .. delta
    })
  end

  if left.line_count ~= right.line_count then
    local delta = right.line_count - left.line_count
    table.insert(changes.informational, {
      type = "line_count_change",
      detail = "Line count changed by " .. delta
    })
  end

  return changes
end

-- =============================================================================
-- Stability Score
-- =============================================================================
-- Elena's stability score: 100 - (breaking*5 + non_breaking*1 + informational*0.5)
-- Clamped to [0, 100].

function calculate_stability(breaking, non_breaking, informational)
  local score = 100 - (breaking * 5 + non_breaking * 1 + informational * 0.5)
  return math.max(0, math.min(100, math.floor(score + 0.5)))
end

-- =============================================================================
-- Vibe Shift
-- =============================================================================
-- Elena's vibe shift: derived from emoji delta.

function calculate_vibe_shift(left_emoji, right_emoji)
  local delta = right_emoji - left_emoji
  if delta == 0 then return "peaceful (no emoji change)"
  elseif delta > 0 and delta <= 3 then return "expressive (+" .. delta .. " emoji)"
  elseif delta < 0 and delta >= -3 then return "minimalist (" .. delta .. " emoji)"
  else return "volatile (emoji delta: " .. delta .. ")"
  end
end

-- =============================================================================
-- JSON Output (deterministic)
-- =============================================================================

local function escape_json_string(s)
  s = s:gsub('\\', '\\\\')
  s = s:gsub('"', '\\"')
  s = s:gsub('\n', '\\n')
  s = s:gsub('\r', '\\r')
  s = s:gsub('\t', '\\t')
  return s
end

local function sorted_keys(t)
  local keys = {}
  for k in pairs(t) do keys[#keys + 1] = k end
  table.sort(keys)
  return keys
end

local function to_json_value(val)
  if type(val) == "string" then
    return '"' .. escape_json_string(val) .. '"'
  elseif type(val) == "number" then
    return tostring(val)
  elseif type(val) == "boolean" then
    return tostring(val)
  elseif type(val) == "nil" then
    return "null"
  elseif type(val) == "table" then
    if #val > 0 then
      local parts = {}
      for _, v in ipairs(val) do
        parts[#parts + 1] = to_json_value(v)
      end
      return "[" .. table.concat(parts, ",") .. "]"
    else
      local keys = sorted_keys(val)
      local parts = {}
      for _, k in ipairs(keys) do
        parts[#parts + 1] = '"' .. escape_json_string(k) .. '":' .. to_json_value(val[k])
      end
      return "{" .. table.concat(parts, ",") .. "}"
    end
  end
  return "null"
end

local function format_json_output(changes, summary)
  local output = {
    summary = {
      breaking = summary.breaking,
      non_breaking = summary.non_breaking,
      informational = summary.informational,
      total = summary.total,
      stability_score = summary.stability_score,
      vibe_shift = summary.vibe_shift
    },
    breaking = {},
    non_breaking = {},
    informational = {}
  }

  for _, c in ipairs(changes.breaking) do
    local entry = { type = c.type, detail = c.detail }
    if c.path then entry.path = c.path end
    if c.method then entry.method = c.method end
    if c.field then entry.field = c.field end
    if c.schema then entry.schema = c.schema end
    if c.value then entry.value = c.value end
    output.breaking[#output.breaking + 1] = entry
  end

  for _, c in ipairs(changes.non_breaking) do
    local entry = { type = c.type, detail = c.detail }
    if c.path then entry.path = c.path end
    if c.method then entry.method = c.method end
    if c.field then entry.field = c.field end
    if c.schema then entry.schema = c.schema end
    output.non_breaking[#output.non_breaking + 1] = entry
  end

  for _, c in ipairs(changes.informational) do
    output.informational[#output.informational + 1] = { type = c.type, detail = c.detail }
  end

  return to_json_value(output)
end

-- =============================================================================
-- Text Output
-- =============================================================================

local function print_diff_text(changes, left_name, right_name, summary)
  print("")
  print(DIFF_COLOR_META .. "=== OpenAPI Diff Report ===" .. DIFF_COLOR_RESET)
  print("")
  print("Comparing:")
  print("  Left:  " .. left_name)
  print("  Right: " .. right_name)
  print("")

  print(DIFF_COLOR_META .. "--- Summary ---" .. DIFF_COLOR_RESET)
  print("  Breaking:         " .. summary.breaking)
  print("  Non-breaking:     " .. summary.non_breaking)
  print("  Informational:    " .. summary.informational)
  print("  Total changes:    " .. summary.total)
  print("  Stability score:  " .. summary.stability_score .. "/100")
  print("  Vibe shift:       " .. summary.vibe_shift)
  print("")

  if #changes.breaking > 0 then
    print(DIFF_COLOR_REMOVE .. "--- Breaking Changes (" .. #changes.breaking .. ") ---" .. DIFF_COLOR_RESET)
    for _, c in ipairs(changes.breaking) do
      print(DIFF_COLOR_REMOVE .. "  [BREAKING] " .. c.detail .. DIFF_COLOR_RESET)
    end
    print("")
  end

  if #changes.non_breaking > 0 then
    print(DIFF_COLOR_ADD .. "--- Non-breaking Changes (" .. #changes.non_breaking .. ") ---" .. DIFF_COLOR_RESET)
    for _, c in ipairs(changes.non_breaking) do
      print(DIFF_COLOR_ADD .. "  [NON-BREAKING] " .. c.detail .. DIFF_COLOR_RESET)
    end
    print("")
  end

  if #changes.informational > 0 then
    print(DIFF_COLOR_CHANGE .. "--- Informational (" .. #changes.informational .. ") ---" .. DIFF_COLOR_RESET)
    for _, c in ipairs(changes.informational) do
      print(DIFF_COLOR_CHANGE .. "  [INFO] " .. c.detail .. DIFF_COLOR_RESET)
    end
    print("")
  end

  if summary.breaking > 0 then
    print(DIFF_COLOR_REMOVE .. "  WARNING: This diff contains breaking changes." .. DIFF_COLOR_RESET)
  elseif summary.total == 0 then
    print(DIFF_COLOR_ADD .. "  No changes detected. The API is stable." .. DIFF_COLOR_RESET)
  else
    print(DIFF_COLOR_ADD .. "  No breaking changes detected." .. DIFF_COLOR_RESET)
  end

  print("")
  print(DIFF_COLOR_META .. "=== End of Report ===" .. DIFF_COLOR_RESET)
  print("")
end

-- =============================================================================
-- Main
-- =============================================================================

local args = {...}
local left_file, right_file
local remote_url
local existential = false
local output_format = "text"

for i, arg in ipairs(args) do
  if arg == "--left" and i < #args then left_file = args[i + 1]
  elseif arg == "--right" and i < #args then right_file = args[i + 1]
  elseif arg == "--local" and i < #args then left_file = args[i + 1]
  elseif arg == "--remote" and i < #args then remote_url = args[i + 1]
  elseif arg == "--self" and i < #args then
    left_file = args[i + 1]
    right_file = args[i + 1]
    existential = true
  elseif arg == "--format" and i < #args then
    output_format = args[i + 1]
  elseif arg == "--help" then
    print("Tent of Trials OpenAPI Diff Tool")
    print("")
    print("Usage:")
    print("  lua tools/openapi_diff.lua --left old.yaml --right new.yaml [--format text|json]")
    print("  lua tools/openapi_diff.lua --local v3.yaml --remote <url>")
    print("  lua tools/openapi_diff.lua --self v3.yaml")
    print("")
    print("Options:")
    print("  --format text    Output in human-readable text (default)")
    print("  --format json    Output deterministic JSON with severity classification")
    os.exit(0)
  end
end

if not left_file then
  print(RED .. "[Diff] No input files specified." .. RESET)
  print(RED .. "[Diff] Use --help for usage instructions." .. RESET)
  os.exit(1)
end

if existential then
  right_file = left_file
end

if remote_url then
  print(YELLOW .. "[Diff] Remote fetching not yet implemented. Using local file." .. RESET)
  right_file = left_file
end

local left = parse_yaml_keywords(left_file)
local right = parse_yaml_keywords(right_file or left_file)

local changes
if existential then
  changes = {
    breaking = {},
    non_breaking = {},
    informational = {}
  }
else
  changes = classify_changes(left, right)
end

local summary = {
  breaking = #changes.breaking,
  non_breaking = #changes.non_breaking,
  informational = #changes.informational,
  total = #changes.breaking + #changes.non_breaking + #changes.informational,
  stability_score = calculate_stability(#changes.breaking, #changes.non_breaking, #changes.informational),
  vibe_shift = calculate_vibe_shift(left.emoji_count, right.emoji_count)
}

if output_format == "json" then
  print(format_json_output(changes, summary))
else
  print_diff_text(changes, left_file, right_file or left_file, summary)
end
