#!/usr/bin/env python3
"""
Автоматическое обновление APP_VERSION и CHANGELOG в frontend/index.html.
Запускается при каждом деплое из deploy.yml.

Логика:
  - APP_VERSION = '1.0.{total_git_commits}'
  - CHANGELOG   = последние 5 дат коммитов, сгруппированные по дате,
                  с emoji по типу conventional commit (feat/fix/docs/…)
"""
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
FRONTEND = ROOT / 'frontend' / 'index.html'

MONTHS_RU = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]

EMOJI_MAP = [
    (r'^feat(\(.+\))?:\s*',     '✨ '),
    (r'^fix(\(.+\))?:\s*',      '🐛 '),
    (r'^docs(\(.+\))?:\s*',     '📚 '),
    (r'^refactor(\(.+\))?:\s*', '⚙️ '),
    (r'^style(\(.+\))?:\s*',    '🎨 '),
    (r'^perf(\(.+\))?:\s*',     '⚡️ '),
    (r'^test(\(.+\))?:\s*',     '🧪 '),
    (r'^ci(\(.+\))?:\s*',       '🚀 '),
    (r'^chore(\(.+\))?:\s*',    '⚙️ '),
]


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT,
                                   stderr=subprocess.DEVNULL).decode('utf-8', errors='replace').strip()


def commit_to_change(msg: str) -> str:
    """Парсит сообщение коммита → строка с emoji для changelog."""
    msg = msg.strip()
    for pattern, emoji in EMOJI_MAP:
        m = re.match(pattern, msg, re.IGNORECASE)
        if m:
            rest = msg[m.end():]
            rest = rest[:1].upper() + rest[1:] if rest else rest
            return emoji + rest
    # Без prefixа
    return '⚙️ ' + msg[:1].upper() + msg[1:] if msg else ''


def escape_js(s: str) -> str:
    """Экранирует строку для вставки в JS-строку в одинарных кавычках."""
    return s.replace('\\', '\\\\').replace("'", "\\'")


def format_date_ru(date_str: str) -> str:
    """'2026-04-06' → '6 апреля 2026'"""
    d = datetime.strptime(date_str, '%Y-%m-%d')
    return f"{d.day} {MONTHS_RU[d.month - 1]} {d.year}"


def count_commits_until(date_str: str) -> int:
    """Сколько коммитов было до конца дня date_str включительно."""
    next_day = (datetime.strptime(date_str, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
    return int(git('rev-list', '--count', f'--before={next_day}', 'HEAD'))


def build_changelog(dates: list[str]) -> list[dict]:
    """Строит записи changelog по дате коммитов."""
    log = git('log', '--pretty=format:%ad|%s', '--date=format:%Y-%m-%d', '--no-merges', '-100')
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for line in log.splitlines():
        if '|' not in line:
            continue
        date, msg = line.split('|', 1)
        if date in dates:
            change = commit_to_change(msg)
            if change:
                groups[date].append(change)

    result = []
    for date_str in dates:
        count = count_commits_until(date_str)
        result.append({
            'version': f'1.0.{count}',
            'date': format_date_ru(date_str),
            'changes': groups[date_str][:8],
        })
    return result


def changelog_to_js(entries: list[dict]) -> str:
    """Сериализует changelog в JS-литерал массива."""
    parts = []
    for entry in entries:
        changes_js = ',\n'.join(f"    '{escape_js(c)}'" for c in entry['changes'])
        parts.append(
            f"  {{\n"
            f"    version: '{entry['version']}',\n"
            f"    date: '{entry['date']}',\n"
            f"    changes: [\n"
            f"{changes_js}\n"
            f"    ]\n"
            f"  }}"
        )
    return '[\n' + ',\n'.join(parts) + '\n]'


def replace_js_array(content: str, var_name: str, new_value: str) -> str:
    """Заменяет `const VAR = [...]` на новое значение (с учётом вложенных скобок)."""
    marker = f'const {var_name} = ['
    start = content.find(marker)
    if start == -1:
        raise ValueError(f'Не найдено: {marker}')
    bracket_start = start + len(marker) - 1  # позиция открывающей [
    depth = 0
    end = bracket_start
    for i in range(bracket_start, len(content)):
        if content[i] == '[':
            depth += 1
        elif content[i] == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
    return content[:bracket_start] + new_value + content[end + 1:]


def main() -> int:
    # ── Версия ──────────────────────────────────────────────────────
    total = int(git('rev-list', '--count', 'HEAD'))
    version = f'1.0.{total}'

    # ── Уникальные даты коммитов (последние 5) ──────────────────────
    log_dates = git('log', '--pretty=format:%ad', '--date=format:%Y-%m-%d', '--no-merges', '-100')
    seen: list[str] = []
    for d in log_dates.splitlines():
        if d not in seen:
            seen.append(d)
        if len(seen) == 5:
            break

    # ── Changelog ───────────────────────────────────────────────────
    entries = build_changelog(seen)
    changelog_js = changelog_to_js(entries)

    # ── Патч index.html ─────────────────────────────────────────────
    content = FRONTEND.read_text(encoding='utf-8')

    # APP_VERSION
    content = re.sub(
        r"const APP_VERSION = '[^']*'",
        f"const APP_VERSION = '{version}'",
        content,
    )

    # CHANGELOG
    content = replace_js_array(content, 'CHANGELOG', changelog_js)

    FRONTEND.write_text(content, encoding='utf-8')

    total_changes = sum(len(e['changes']) for e in entries)
    print(f'✓ APP_VERSION → {version}')
    print(f'✓ CHANGELOG   → {len(entries)} записей, {total_changes} изменений')
    for e in entries:
        print(f'   {e["version"]}  {e["date"]}  ({len(e["changes"])} items)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
