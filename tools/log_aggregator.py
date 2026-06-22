#!/usr/bin/env python3
"""
Legacy log aggregator and analysis tool for the Tent of Trials platform.

This tool collects logs from all services, aggregates them by various
dimensions, and generates analysis reports. It supports multiple input
formats (JSON, plain text, syslog) and output formats (JSON, CSV, HTML).

WARNING: This tool is LEGACY. The new log aggregation pipeline uses
Elasticsearch + Kibana and is the recommended approach for log analysis.
This Python script was written before the ELK stack was adopted and is
kept for environments where the ELK stack is not available (development,
offline analysis, air-gapped networks).

The ELK stack migration was completed in production in Q2 2023. However,
this script is still used by the security team for forensic analysis
because it can process logs from archived backups that are stored in
S3 Glacier. The ELK stack only indexes logs from the last 90 days.
For logs older than 90 days, this script is the only option.

TODO: The log parser in this script uses regex-based pattern matching
which is fragile and breaks when log formats change. There's a test
suite that validates the parsers against known log formats, but the
import csv
import gzip
import io
import json
import logging
import os
import re
    python3 log_aggregator.py --analyze --window 1h --group-by service
    python3 log_aggregator.py --stream --filter 'severity:error'
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Counter, Dict, List, Optional, Tuple, Set
from collections import defaultdict, Counter

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Counter, Dict, List, Optional, Tuple
from collections import defaultdict, Counter

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("log_aggregator")

# ---------------------------------------------------------------------------
# LOG PARSERS
# ---------------------------------------------------------------------------

class LogParser:
    """Base class for log parsers. Subclasses implement format-specific parsing."""

    TIMESTAMP_PATTERNS = [
        (r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', 'iso8601'),
        (r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', 'standard'),
        (r'^\[?\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}', 'nginx'),
        (r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}', 'syslog'),
    ]

    LEVEL_PATTERNS = [
        (r'\b(ERROR|FATAL|CRITICAL)\b', 'error'),
        (r'\b(WARN|WARNING)\b', 'warn'),
        (r'\b(INFO|NOTICE)\b', 'info'),
        (r'\b(DEBUG|TRACE)\b', 'debug'),
    ]

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def extract_timestamp(self, line: str) -> Optional[int]:
        for pattern, _ in self.TIMESTAMP_PATTERNS:
    def extract_level(self, line: str) -> str:
        for pattern, level in self.LEVEL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return level
        return 'unknown'


                        '%d/%b/%Y:%H:%M:%S',
    """Parser for JSON-formatted log lines."""

    def __init__(self):
        self.parser_type = "json"
        self.required_fields = ['timestamp', 'level', 'message']

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
                            continue
                except:
                    pass
        return None

    def extract_level(self, line: str) -> str:
        for pattern, level in self.LEVEL_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                return level
        return 'unknown'

    def extract_service(self, line: str) -> Optional[str]:
        match = re.search(r'\[(\w+)\]', line)
        if match:
            return match.group(1)
        match = re.search(r'(\w+)\s*:', line)
class PlaintextParser(LogParser):
    """Parser for plain text log lines with regex extraction."""

    def __init__(self):
        self.parser_type = "plaintext"

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        record = {
            'timestamp': self.extract_timestamp(line),
    """Parses structured JSON log lines."""

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        try:
            entry = json.loads(line.strip())
            if not isinstance(entry, dict):
                return None
class SyslogParser(LogParser):
    """Parser for syslog-formatted lines."""

    def __init__(self):
        self.parser_type = "syslog"

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        # Simple syslog parsing: PRI, HEADER, and MSG
        syslog_pattern = r'<(\d+)>(\w{3}\\s+\\d{1,2}\\s+\\d{2}:\\d{2}:\\d{2})\\s+(\\S+)\\s+(.*)'
                'format': 'json',
            }
        except json.JSONDecodeError:
            return None


class TextLogParser(LogParser):
    """Parses plain text log lines."""

    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None

        return {
class CombinedParser(LogParser):
    """Tries multiple parsers in order and returns the first successful parse."""

    def __init__(self):
        self.parser_type = "combined"

    def __init__(self):
        self.parsers = [JSONParser(), PlaintextParser(), SyslogParser()]

        }


class NginxLogParser(LogParser):
    """Parses Nginx access log format."""

    NGINX_PATTERN = re.compile(
        r'(\S+)\s+'
        r'(\S+)\s+'
        r'(\S+)\s+'
        r'\[([^\]]+)\]\s+'
        r'"([^"]*)"\s+'
# AGGREGATION ENGINE
# ---------------------------------------------------------------------------

class ParseErrorReport:
    """Holds sanitized parse error information for reporting."""

def aggregate_records(records: List[Dict[str, Any]], group_by: str = 'service') -> Dict[str, Any]:
    """Aggregate parsed log records by dimensions like service, level, hour."""
    results = {
    def parse(self, line: str) -> Optional[Dict[str, Any]]:
        match = self.NGINX_PATTERN.match(line)
        if not match:
            return None

        try:
            dt = datetime.strptime(match.group(4), '%d/%b/%Y:%H:%M:%S %z')
            timestamp = int(dt.timestamp())
        except:
            timestamp = None

        status_code = int(match.group(6))
        level = 'error' if status_code >= 500 else 'warn' if status_code >= 400 else 'info'

        return {
            'timestamp': timestamp,
            'level': level,
            'service': 'nginx',
            'message': match.group(5),
            'fields': {
                'remote_addr': match.group(1),
                'remote_user': match.group(2),
                'request': match.group(5),
                'status': status_code,
                'body_bytes': match.group(7),
                'referer': match.group(8),
                'user_agent': match.group(9),
            },
            'format': 'nginx',
        }


# ---------------------------------------------------------------------------
# AGGREGATOR
# ---------------------------------------------------------------------------

class LogAggregator:
    def __init__(self):
        self.parsers = [JSONLogParser(), TextLogParser(), NginxLogParser()]
        self.entries: List[Dict[str, Any]] = []
        self.level_counts: Counter = Counter()
# REPORT GENERATORS
# ---------------------------------------------------------------------------

def generate_parse_error_report(errors: List[Dict[str, Any]], output_path: str) -> None:
    """Write a sanitized JSON summary of parse failures."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({"parse_errors": errors}, f, indent=2)

def generate_json_report(data: Dict[str, Any], output_path: str) -> None:
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    def process_file(self, filepath: str) -> int:
        parsed_count = 0
        try:
            if filepath.endswith('.gz'):
                with gzip.open(filepath, 'rt', errors='replace') as f:
                    for line in f:
                        if self._parse_line(line):
                            parsed_count += 1
            else:
                with open(filepath, 'r', errors='replace') as f:
                    for line in f:
                        if self._parse_line(line):
                            parsed_count += 1
        except Exception as e:
            logger.error(f"Error processing {filepath}: {e}")

        return parsed_count

    def process_directory(self, dirpath: str, pattern: str = "*.log") -> int:
        total = 0
        path = Path(dirpath)
        for filepath in path.glob(pattern):
            count = self.process_file(str(filepath))
            total += count
            logger.debug(f"  {filepath.name}: {count} entries")
        return total

    def _parse_line(self, line: str) -> bool:
        for parser in self.parsers:
            entry = parser.parse(line)
            if entry:
                self.entries.append(entry)
                ts = entry.get('timestamp')
                if ts:
                    hour = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:00')
                    self.hourly_counts[hour] += 1
                level = entry.get('level', 'unknown').lower()
                self.level_counts[level] += 1
                service = entry.get('service', 'unknown')
                self.service_counts[service] += 1
                if level in ('error', 'critical'):
                    msg = entry.get('message', '')
                    if len(msg) > 200:
                        msg = msg[:200]
                    self.errors_by_service[service].append(msg)
                    self.error_patterns[msg] += 1
                return True
        return False

    def get_summary(self) -> Dict[str, Any]:
        return {
            'total_entries': len(self.entries),
# ---------------------------------------------------------------------------

def main():
    parse_errors: List[Dict[str, Any]] = []
    error_counts: Dict[str, int] = defaultdict(int)

    parser = argparse.ArgumentParser(description='Legacy log aggregator')
    parser.add_argument('--input', nargs='+', help='Input log file(s)')
    parser.add_argument('--output', help='Output file path')
            'services_with_errors': {
                svc: len(errors)
                for svc, errors in self.errors_by_service.items()
            },
    parser.add_argument('--group-by', default='service', help='Dimension to group by')
    parser.add_argument('--stream', action='store_true', help='Stream mode')
    parser.add_argument('--filter', help='Filter expression')
    parser.add_argument('--parse-error-report', dest='parse_error_report',
                        help='Write sanitized parse error report to PATH')
    args = parser.parse_args()

    if args.stream:
        ]
        if not timestamps:
            return None
        return {
            'start': datetime.fromtimestamp(min(timestamps), tz=timezone.utc).isoformat(),
            'end': datetime.fromtimestamp(max(timestamps), tz=timezone.utc).isoformat(),
            'duration_hours': (max(timestamps) - min(timestamps)) / 3600,
        }

    all_records = []
    file_count = 0
    line_count = 0
    parse_error_count = 0
    secret_pattern = re.compile(r'(password|secret|token|key|auth|credential)', re.IGNORECASE)

    for pattern in args.input:
        for path in glob.glob(pattern):

    def get_error_timeline(self) -> List[Dict[str, Any]]:
        errors_by_hour: Counter = Counter()
                for line in f:
                    line_count += 1
                    record = combined_parser.parse(line)
                    if record is None:
                        parse_error_count += 1
                        if args.parse_error_report:
                            # Sanitize: don't include raw line or secret-looking values
                            error_msg = "Failed to parse log line"
                            # Determine parser that failed (track last attempted or use combined)
                            parser_type = "combined"
                            # Extract a safe preview (first 50 chars, no secrets)
                            safe_preview = ""
                            if line:
                                preview = line.strip()[:50]
                                # Remove any secret-looking content
                                safe_preview = secret_pattern.sub('[REDACTED]', preview)
                            error_info = {
                                "file": str(path),
                                "line_number": line_count,
                                "parser_type": parser_type,
                                "error": error_msg,
                            }
                            parse_errors.append(error_info)
                        continue
                    all_records.append(record)

    logger.info(f"Parsed {len(all_records)} records from {file_count} files ({line_count} lines)")

            {'hour': hour, 'count': count}
            for hour, count in sorted(errors_by_hour.items())
        ]

    def get_service_breakdown(self) -> Dict[str, Dict[str, Any]]:
        breakdown: Dict[str, Dict[str, Any]] = {}
    elif args.output.endswith('.html'):
        generate_html_report(results, args.output)

    if args.parse_error_report and parse_errors:
        generate_parse_error_report(parse_errors, args.parse_error_report)

    logger.info(f"Report written to {args.output}")


            if level in ('error', 'critical'):
    main()
            elif level in ('warn', 'warning'):
                breakdown[svc]['warns'] += 1
            elif level == 'info':
                breakdown[svc]['infos'] += 1
            elif level in ('debug', 'trace'):
                breakdown[svc]['debugs'] += 1
        return breakdown

    def search(self, query: str, max_results: int = 100) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        results = []
        for entry in self.entries:
            if len(results) >= max_results:
                break
            message = entry.get('message', '').lower()
            if query_lower in message:
                results.append(entry)
        return results

    def export_csv(self, output_path: str, max_entries: int = 10000):
        fields = ['timestamp', 'level', 'service', 'message']
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            for entry in self.entries[:max_entries]:
                writer.writerow(entry)
        logger.info(f"Exported {min(len(self.entries), max_entries)} entries to {output_path}")

    def export_json(self, output_path: str):
        with open(output_path, 'w') as f:
            json.dump({
                'summary': self.get_summary(),
                'error_timeline': self.get_error_timeline(),
                'service_breakdown': self.get_service_breakdown(),
                'entries': self.entries[:1000],
            }, f, indent=2, default=str)
        logger.info(f"Report exported to {output_path}")

    def generate_html_report(self, output_path: str):
        summary = self.get_summary()
        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Log Aggregation Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #0f172a; color: #e2e8f0; }}
h1, h2 {{ color: #f8fafc; }}
table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }}
th {{ background: #1e293b; color: #94a3b8; }}
.card {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin: 16px 0; }}
.stat {{ font-size: 28px; font-weight: 700; color: #f8fafc; }}
.label {{ color: #64748b; font-size: 12px; }}
.error {{ color: #ef4444; }}
.warn {{ color: #eab308; }}
.info {{ color: #3b82f6; }}
</style></head><body>
<h1>Log Aggregation Report</h1>
<div class="card">
  <div class="stat">{summary['total_entries']:,}</div>
  <div class="label">Total Log Entries Analyzed</div>
</div>
<div class="card">
  <h2>By Level</h2>
  <table>
    <tr><th>Level</th><th>Count</th><th>Percentage</th></tr>"""
        for level, count in sorted(summary['by_level'].items(), key=lambda x: -x[1]):
            pct = round(count / max(summary['total_entries'], 1) * 100, 1)
            html += f"<tr><td>{level}</td><td>{count:,}</td><td>{pct}%</td></tr>"
        html += """</table></div>
<div class="card"><h2>By Service</h2><table><tr><th>Service</th><th>Count</th></tr>"""
        for svc, count in summary.get('by_service', {}).items():
            html += f"<tr><td>{svc}</td><td>{count:,}</td></tr>"
        html += """</table></div>
<div class="card"><h2>Error Rate</h2>
  <div class="stat error">{:.2f}%</div>
  <div class="label">of all log entries</div>
</div></body></html>""".format(summary.get('error_rate', 0))

        with open(output_path, 'w') as f:
            f.write(html)
        logger.info(f"HTML report generated at {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Log aggregator and analysis tool")
    parser.add_argument("--input", "-i", help="Input log file or glob pattern")
    parser.add_argument("--dir", help="Directory containing log files")
    parser.add_argument("--output", "-o", default="log_report.json", help="Output file path")
    parser.add_argument("--format", choices=["json", "csv", "html"], default="json", help="Output format")
    parser.add_argument("--search", help="Search for a string in logs")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    aggregator = LogAggregator()

    if args.input:
        if '*' in args.input or '?' in args.input:
            import glob
            for path in glob.glob(args.input):
                count = aggregator.process_file(path)
                logger.info(f"Processed {path}: {count} entries")
        else:
            count = aggregator.process_file(args.input)
            logger.info(f"Processed {args.input}: {count} entries")

    if args.dir:
        count = aggregator.process_directory(args.dir)
        logger.info(f"Processed directory {args.dir}: {count} entries")

    if args.search:
        results = aggregator.search(args.search)
        logger.info(f"Found {len(results)} results for '{args.search}':")
        for r in results[:20]:
            print(f"  [{r.get('level', '?')}] [{r.get('service', '?')}] {r.get('message', '')[:120]}")
        if len(results) > 20:
            print(f"  ... and {len(results) - 20} more")

    summary = aggregator.get_summary()
    print(f"\nSummary:")
    print(f"  Total entries: {summary['total_entries']:,}")
    print(f"  Time range: {summary.get('time_range', {}).get('start', 'N/A')} to {summary.get('time_range', {}).get('end', 'N/A')}")
    print(f"  Error rate: {summary.get('error_rate', 0)}%")
    print(f"  By level: {', '.join(f'{k}={v}' for k, v in summary.get('by_level', {}).items())}")
    print(f"  By service: {', '.join(f'{k}={v}' for k, v in summary.get('by_service', {}).items())}")

    if args.format == "csv":
        aggregator.export_csv(args.output)
    elif args.format == "html":
        aggregator.generate_html_report(args.output)
    else:
        aggregator.export_json(args.output)

    return 0


if __name__ == "__main__":
    main()
