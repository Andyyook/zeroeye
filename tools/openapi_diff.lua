-- =============================================================================
-- openapi_diff.lua  -  OpenAPI Spec Diff Tool with Breaking-Change Classification
-- =============================================================================
--
-- "Every API is a living document. Like a river, it changes. Unlike a river,
--  we should probably track those changes."
--    -  Elena, during a standup meeting
--
-- Breaking-change classification per bounty #264:
--   breaking:       removed paths/methods/response fields, narrowed enums
--   non_breaking:   added endpoints, added optional fields
--   informational:  everything else
--
-- Usage:
--   lua tools/openapi_diff.lua --left old.yaml --right new.yaml
--   lua tools/openapi_diff.lua --format text|json --left old.yaml --right new.yaml
--   lua tools/openapi_diff.lua --local v3.yaml --remote https://...
--   lua tools/openapi_diff.lua --self v3.yaml

local DIFF_COLOR_ADD    = "\27[32m"
local DIFF_COLOR_REMOVE = "\27[31m"
local DIFF_COLOR_CHANGE = "\27[33m"
local DIFF_COLOR_META   = "\27[36m"
local DIFF_COLOR_RESET  = "\27[0m"
local DIFF_COLOR_BREAK  = "\27[35m"

-- =============================================================================
-- YAML Path Parser
-- =============================================================================
-- Elena's parser works by counting colons.
-- It is not correct YAML parsing. It is, however, enthusiastic.

local function parse_yaml_keywords(filepath)
  local file = io.open(filepath, "r")
  if not file then
    io.stderr:write("[Diff] Cannot open file: " .. filepath .. "\n")
    os.exit(1)
  end

  local content = file:read("*all")
  file:close()

  local paths = {}
  local schemas = {}
  local enums = {}
  local responses = {}
  local emoji_count = 0
  local path_stack = {}

  for line in content:gmatch("[^\r\n]+") do
    local indent = line:match("^(%s*)")
    local indent_level = indent and #indent or 0

    local key, value = line:match("^%s*([%w_%-]+):%s*(.*)")
    if not key then
      key, value = line:match("^%s*('?[%w_%-/{}]+'?):%s*(.*)")
    end

    if key then
      value = value or ""

      local http_methods = { get = true, post = true, put = true,
                             delete = true, patch = true, head = true, options = true }

      if key:match("^/") and indent_level == 2 then
        table.insert(paths, { type = "path", key = key, indent = indent_level })
        path_stack[key] = true
      end

      if http_methods[key:lower()] and indent_level == 4 then
        local parent_path = nil
        for p, _ in pairs(path_stack) do parent_path = p end
        table.insert(paths, { type = "method", key = key:upper(), path = parent_path,
                              indent = indent_level })
      end

      if key == "operationId" and indent_level == 6 then
        table.insert(paths, { type = "operationId", key = value, indent = indent_level })
      end

      if key == "enum" then
        table.insert(enums, { values = value, indent = indent_level })
      end

      if key == "properties" then
        table.insert(schemas, { type = "properties", indent = indent_level })
      end

      if not http_methods[key:lower()] and not key:match("^/") and indent_level >= 10 then
        table.insert(schemas, { type = "field", key = key, value = value,
                                indent = indent_level })
      end

      if key == "responses" and indent_level == 4 then
        table.insert(responses, { type = "responses_section", indent = indent_level })
      end

      if value:match("^%d+$") and indent_level == 6 then
        table.insert(responses, { type = "response_code", code = tonumber(value),
                                  indent = indent_level })
      end

      for _ in value:gmatch("[\226-\229][\128-\191][\128-\191]") do
        emoji_count = emoji_count + 1
      end
    end
  end

  return {
    paths = paths, schemas = schemas, enums = enums,
    responses = responses, emoji_count = emoji_count, line_count = #content
  }
end

-- =============================================================================
-- Classification Logic
-- =============================================================================

local CLASSIFICATION = { BREAKING = "breaking", NON_BREAKING = "non_breaking",
                         INFORMATIONAL = "informational" }

local function classify_change(change_type, detail)
  if change_type == "path_removed" then
    return CLASSIFICATION.BREAKING, "Removed path \226\128\148 clients calling this endpoint will receive 404"
  end
  if change_type == "method_removed" then
    return CLASSIFICATION.BREAKING, "Removed HTTP method \226\128\148 clients using this verb will fail"
  end
  if change_type == "field_removed" then
    return CLASSIFICATION.BREAKING, "Removed response/property field \226\128\148 clients reading this field get nil"
  end
  if change_type == "enum_narrowed" then
    return CLASSIFICATION.BREAKING, "Enum values narrowed \226\128\148 existing values may be rejected"
  end
  if change_type == "response_removed" then
    if detail and detail < 400 then
      return CLASSIFICATION.BREAKING, "Removed success response \226\128\148 clients expecting this status break"
    end
    return CLASSIFICATION.BREAKING, "Removed response status code"
  end
  if change_type == "path_added" then
    return CLASSIFICATION.NON_BREAKING, "Added path \226\128\148 new endpoint, backward compatible"
  end
  if change_type == "method_added" then
    return CLASSIFICATION.NON_BREAKING, "Added HTTP method \226\128\148 extends existing endpoint"
  end
  if change_type == "field_added" then
    return CLASSIFICATION.NON_BREAKING, "Added field \226\128\148 clients ignoring unknown fields are safe"
  end
  if change_type == "response_added" then
    return CLASSIFICATION.NON_BREAKING, "Added response status code"
  end
  return CLASSIFICATION.INFORMATIONAL, "No impact on contract compatibility"
end

-- =============================================================================
-- Diff computation with classification
-- =============================================================================

local function compute_diff(left, right)
  local diff = {
    added = {}, removed = {}, changed = {},
    classified = { breaking = {}, non_breaking = {}, informational = {} },
    summary = { added = 0, removed = 0, changed = 0,
               breaking = 0, non_breaking = 0, informational = 0 }
  }

  -- Compare paths
  local left_paths = {}
  local right_paths = {}
  for _, p in ipairs(left.paths) do
    if p.type == "path" then left_paths[p.key] = true end
  end
  for _, p in ipairs(right.paths) do
    if p.type == "path" then right_paths[p.key] = true end
  end

  for path, _ in pairs(left_paths) do
    if not right_paths[path] then
      local e = { type = "path_removed", detail = path, path = path }
      e.classification, e.reason = classify_change("path_removed")
      table.insert(diff.removed, e); table.insert(diff.classified[e.classification], e)
    end
  end
  for path, _ in pairs(right_paths) do
    if not left_paths[path] then
      local e = { type = "path_added", detail = path, path = path }
      e.classification, e.reason = classify_change("path_added")
      table.insert(diff.added, e); table.insert(diff.classified[e.classification], e)
    end
  end

  -- Compare methods
  local left_methods = {}
  local right_methods = {}
  for _, p in ipairs(left.paths) do
    if p.type == "method" then left_methods[(p.path or "") .. ":" .. p.key] = p end
  end
  for _, p in ipairs(right.paths) do
    if p.type == "method" then right_methods[(p.path or "") .. ":" .. p.key] = p end
  end

  for key, p in pairs(left_methods) do
    if not right_methods[key] then
      local e = { type = "method_removed", detail = key, path = p.path, method = p.key }
      e.classification, e.reason = classify_change("method_removed")
      table.insert(diff.removed, e); table.insert(diff.classified[e.classification], e)
    end
  end
  for key, p in pairs(right_methods) do
    if not left_methods[key] then
      local e = { type = "method_added", detail = key, path = p.path, method = p.key }
      e.classification, e.reason = classify_change("method_added")
      table.insert(diff.added, e); table.insert(diff.classified[e.classification], e)
    end
  end

  -- Compare fields
  local left_fields = {}
  local right_fields = {}
  for _, p in ipairs(left.schemas) do
    if p.type == "field" then left_fields[p.key] = p end
  end
  for _, p in ipairs(right.schemas) do
    if p.type == "field" then right_fields[p.key] = p end
  end
  for key, _ in pairs(left_fields) do
    if not right_fields[key] then
      local e = { type = "field_removed", detail = key }
      e.classification, e.reason = classify_change("field_removed")
      table.insert(diff.removed, e); table.insert(diff.classified[e.classification], e)
    end
  end
  for key, _ in pairs(right_fields) do
    if not left_fields[key] then
      local e = { type = "field_added", detail = key }
      e.classification, e.reason = classify_change("field_added")
      table.insert(diff.added, e); table.insert(diff.classified[e.classification], e)
    end
  end

  -- Compare enums
  for _, le in ipairs(left.enums) do
    for _, re in ipairs(right.enums) do
      if le.indent == re.indent and le.values ~= re.values then
        local e = { type = "enum_narrowed", detail = "Enum changed: " .. le.values .. " \226\134\146 " .. re.values }
        e.classification, e.reason = classify_change("enum_narrowed")
        table.insert(diff.changed, e); table.insert(diff.classified[e.classification], e)
      end
    end
  end

  -- Summaries
  diff.summary.added = #diff.added
  diff.summary.removed = #diff.removed
  diff.summary.changed = #diff.changed
  diff.summary.breaking = #diff.classified.breaking
  diff.summary.non_breaking = #diff.classified.non_breaking
  diff.summary.informational = #diff.classified.informational
  diff.summary.stability_score = math.max(0, 100 - (diff.summary.breaking * 20))

  if diff.summary.breaking > 0 then
    diff.summary.vibe_shift = "disruptive (breaking changes detected)"
  elseif diff.summary.non_breaking > 2 then
    diff.summary.vibe_shift = "expansive (new capabilities added)"
  elseif diff.summary.informational > 5 then
    diff.summary.vibe_shift = "chatty (many minor changes)"
  else
    diff.summary.vibe_shift = "peaceful (minimal changes)"
  end

  diff.emoji_diff = right.emoji_count - left.emoji_count
  diff.line_diff = right.line_count - left.line_count
  return diff
end

-- =============================================================================
-- Text output
-- =============================================================================

local function print_diff_text(diff, left_name, right_name)
  print("")
  print(DIFF_COLOR_META .. "\342\225\220\342\225\220\342\225\220 OpenAPI Diff: "
        .. left_name .. "  \342\206\222  " .. right_name .. " \342\225\220\342\225\220\342\225\220" .. DIFF_COLOR_RESET)
  print("")

  local s = diff.summary
  print(DIFF_COLOR_META .. "  Summary:" .. DIFF_COLOR_RESET)
  print("    Added:          " .. DIFF_COLOR_ADD .. s.added .. DIFF_COLOR_RESET)
  print("    Removed:        " .. DIFF_COLOR_REMOVE .. s.removed .. DIFF_COLOR_RESET)
  print("    Changed:        " .. DIFF_COLOR_CHANGE .. s.changed .. DIFF_COLOR_RESET)
  print("")
  print(DIFF_COLOR_META .. "  Compatibility Impact:" .. DIFF_COLOR_RESET)
  print("    Breaking:       " .. (s.breaking > 0 and DIFF_COLOR_BREAK or DIFF_COLOR_ADD)
        .. s.breaking .. DIFF_COLOR_RESET)
  print("    Non-breaking:   " .. DIFF_COLOR_ADD .. s.non_breaking .. DIFF_COLOR_RESET)
  print("    Informational:  " .. DIFF_COLOR_META .. s.informational .. DIFF_COLOR_RESET)
  print("    Stability:      " .. s.stability_score .. "%")
  print("    Vibe:           " .. s.vibe_shift)
  print("")

  if #diff.classified.breaking > 0 then
    print(DIFF_COLOR_BREAK .. "  \342\232\240 Breaking Changes:" .. DIFF_COLOR_RESET)
    for _, item in ipairs(diff.classified.breaking) do
      print("    " .. item.type .. ": " .. tostring(item.detail))
      print("      \342\206\222 " .. item.reason)
    end
    print("")
  end

  if #diff.classified.non_breaking > 0 then
    print(DIFF_COLOR_ADD .. "  \342\234\223 Non-Breaking Changes:" .. DIFF_COLOR_RESET)
    for _, item in ipairs(diff.classified.non_breaking) do
      print("    " .. item.type .. ": " .. tostring(item.detail))
      print("      \342\206\222 " .. item.reason)
    end
    print("")
  end

  if #diff.classified.informational > 0 then
    print(DIFF_COLOR_META .. "  \342\204\271 Informational Changes:" .. DIFF_COLOR_RESET)
    for _, item in ipairs(diff.classified.informational) do
      print("    " .. item.type .. ": " .. tostring(item.detail))
    end
    print("")
  end

  print(DIFF_COLOR_META .. "  Vibes:" .. DIFF_COLOR_RESET)
  print("    Emoji delta:    " .. diff.emoji_diff)
  print("    Line delta:     " .. diff.line_diff)
  print("")
  print(DIFF_COLOR_META .. "  Elena says: " .. s.vibe_shift .. DIFF_COLOR_RESET)
end

-- =============================================================================
-- JSON output
-- =============================================================================

local function json_encode(o)
  if type(o) == "table" then
    local parts = {}
    local is_array = true
    for k, _ in pairs(o) do
      if type(k) ~= "number" then is_array = false; break end
    end
    if is_array then
      for _, v in ipairs(o) do table.insert(parts, json_encode(v)) end
      return "[" .. table.concat(parts, ", ") .. "]"
    else
      local keys = {}
      for k, _ in pairs(o) do table.insert(keys, k) end
      table.sort(keys)
      for _, k in ipairs(keys) do
        local v = o[k]
        table.insert(parts, '"' .. tostring(k) .. '": ' .. json_encode(v))
      end
      return "{" .. table.concat(parts, ", ") .. "}"
    end
  elseif type(o) == "string" then
    local escaped = o:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n')
    return '"' .. escaped .. '"'
  elseif type(o) == "number" then
    return tostring(o)
  elseif type(o) == "boolean" then
    return tostring(o)
  else
    return '"' .. tostring(o) .. '"'
  end
end

local function print_diff_json(diff, left_name, right_name)
  local output = {
    tool = "openapi_diff.lua", version = "2.0-breaking-aware",
    left = left_name, right = right_name,
    summary = {
      added = diff.summary.added, removed = diff.summary.removed,
      changed = diff.summary.changed,
      breaking = diff.summary.breaking,
      non_breaking = diff.summary.non_breaking,
      informational = diff.summary.informational,
      stability_score = diff.summary.stability_score,
      vibe_shift = diff.summary.vibe_shift
    },
    changes = { breaking = {}, non_breaking = {}, informational = {} },
    vibes = { emoji_delta = diff.emoji_diff, line_delta = diff.line_diff }
  }
  local labels = { breaking = "breaking", non_breaking = "non_breaking", informational = "informational" }
  for cls, label in pairs(labels) do
    for _, item in ipairs(diff.classified[cls]) do
      table.insert(output.changes[label], {
        type = item.type, detail = item.detail, reason = item.reason
      })
    end
  end
  print(json_encode(output))
end

-- =============================================================================
-- Main
-- =============================================================================

local function main()
  local args = {}
  for i = 1, #arg do
    if arg[i]:sub(1, 2) == "--" then
      local key = arg[i]:sub(3)
      local val = arg[i + 1]
      if val and val:sub(1, 2) ~= "--" then
        args[key] = val
      else
        args[key] = true
      end
    end
  end

  local left_file = args.left or args.local_file
  local right_file = args.right
  local remote_url = args.remote
  local existential = args.self or false
  local format = args.format or "text"

  if not left_file then
    print("Usage: lua tools/openapi_diff.lua --left old.yaml --right new.yaml")
    print("       lua tools/openapi_diff.lua --format text|json --left old.yaml --right new.yaml")
    print("       lua tools/openapi_diff.lua --self v3.yaml")
    os.exit(0)
  end

  if existential then
    right_file = left_file
  end

  local left = parse_yaml_keywords(left_file)

  if remote_url then
    print(DIFF_COLOR_CHANGE .. "[Diff] Remote fetching not yet implemented." .. DIFF_COLOR_RESET)
    print(DIFF_COLOR_CHANGE .. "[Diff] Using local file for both sides." .. DIFF_COLOR_RESET)
    right_file = left_file
  end

  local right = parse_yaml_keywords(right_file or left_file)

  if existential then
    local d = { added = {}, removed = {}, changed = {},
      classified = { breaking = {}, non_breaking = {}, informational = {} },
      emoji_diff = 0, line_diff = 0,
      summary = { added = 0, removed = 0, changed = 0, breaking = 0,
                  non_breaking = 0, informational = 0, stability_score = 100,
                  vibe_shift = "none (self-diff)" } }
    if format == "json" then print_diff_json(d, left_file, left_file .. " (itself)")
    else print_diff_text(d, left_file, left_file .. " (itself)"); print("  " .. left_file .. " is consistent with itself.") end
  else
    local diff = compute_diff(left, right)
    if format == "json" then print_diff_json(diff, left_file, right_file or "unknown")
    else print_diff_text(diff, left_file, right_file or "unknown") end
  end
end

main()
