#!/usr/bin/env python3
"""
SUMMARY.md의 목차를 index.md(GitHub Pages 홈)에 자동 동기화하는 스크립트.

SUMMARY.md를 single source of truth로 사용하여 index.md를 생성합니다.
- 마크다운 리스트 → 테이블 형식으로 변환
- .md 링크 → {{ site.baseurl }}/.html 링크로 변환
- Jekyll front matter 자동 추가
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = REPO_ROOT / "SUMMARY.md"
INDEX_PATH = REPO_ROOT / "index.md"

INDEX_HEADER = """\
---
layout: default
title: Home
nav_order: 0
permalink: /
---

# CS Knowledge Base

작성자가 매번 헷갈려하는 CS 지식들을 정리하는 저장소입니다.
{: .fs-6 .fw-300 }

---

## 목차

"""

INDEX_FOOTER = """
---

<sub>이 저장소는 [GitHub Pages](https://iamyunjuda.github.io/cs-knowledge-base/)로 자동 배포됩니다.</sub>
"""


def convert_md_link_to_jekyll(md_link: str) -> str:
    """[title](category/file.md) → [title]({{ site.baseurl }}/category/file.html)"""
    def replacer(m):
        title = m.group(1)
        path = m.group(2)
        # .md → .html, add baseurl
        html_path = re.sub(r'\.md$', '.html', path)
        return f'[{title}]({{{{ site.baseurl }}}}/{html_path})'
    return re.sub(r'\[([^\]]+)\]\(([^)]+\.md)\)', replacer, md_link)


def parse_readme_toc(readme_text: str) -> str:
    """SUMMARY.md의 목차 섹션을 파싱하여 index.md용 테이블 형식으로 변환"""
    lines = readme_text.split('\n')
    output = []
    in_toc = False
    current_section = None
    table_started = False

    for line in lines:
        # 목차 시작 감지 (SUMMARY.md는 '# 목차'로 시작)
        if line.strip() in ('# 목차', '## 목차'):
            in_toc = True
            continue

        if not in_toc:
            continue

        # 섹션 헤더 (### ...)
        section_match = re.match(r'^### (.+)$', line)
        if section_match:
            current_section = section_match.group(1)
            if table_started:
                output.append('')  # 섹션 간 빈 줄
            output.append(f'### {current_section}')
            output.append('')
            output.append('| 주제 | 키워드 |')
            output.append('|:-----|:-------|')
            table_started = True
            continue

        # 주제 항목 (- [title](path))
        item_match = re.match(r'^- \[(.+?)\]\((.+?\.md)\)\s*$', line)
        if item_match and current_section:
            title = item_match.group(1)
            path = item_match.group(2)
            html_path = re.sub(r'\.md$', '.html', path)
            jekyll_link = f'[{title}]({{{{ site.baseurl }}}}/{html_path})'
            # 키워드는 다음 줄에서 가져올 것이므로 임시 저장
            output.append(f'| {jekyll_link} | __KEYWORDS_PLACEHOLDER__ |')
            continue

        # 키워드 줄 (  - 설명...)
        keyword_match = re.match(r'^\s+- (.+)$', line)
        if keyword_match and output and '__KEYWORDS_PLACEHOLDER__' in output[-1]:
            keywords = keyword_match.group(1)
            # 키워드를 짧게 요약 (쉼표 구분 항목 추출)
            short_keywords = extract_keywords(keywords)
            output[-1] = output[-1].replace('__KEYWORDS_PLACEHOLDER__', short_keywords)
            continue

        # 빈 줄 무시
        if line.strip() == '':
            continue

    # 아직 placeholder가 남아있으면 빈 문자열로 대체
    output = [l.replace('__KEYWORDS_PLACEHOLDER__', '') for l in output]

    return '\n'.join(output)


def extract_keywords(description: str) -> str:
    """설명 텍스트에서 주요 키워드를 추출"""
    # 쉼표로 구분된 항목들을 키워드로 사용
    parts = [p.strip() for p in description.split(',')]
    # 너무 긴 항목은 줄임
    keywords = []
    for part in parts:
        # 괄호 안의 세부사항 제거하여 간결하게
        short = re.sub(r'\([^)]*\)', '', part).strip()
        if short:
            keywords.append(short)
    return ', '.join(keywords)


def main():
    if not SUMMARY_PATH.exists():
        print(f"ERROR: {SUMMARY_PATH} not found", file=sys.stderr)
        sys.exit(1)

    summary_text = SUMMARY_PATH.read_text(encoding='utf-8')
    toc_content = parse_readme_toc(summary_text)

    index_content = INDEX_HEADER + toc_content + '\n' + INDEX_FOOTER

    # 기존 index.md와 비교
    if INDEX_PATH.exists():
        existing = INDEX_PATH.read_text(encoding='utf-8')
        if existing == index_content:
            print("index.md is already up to date.")
            return

    INDEX_PATH.write_text(index_content, encoding='utf-8')
    print(f"index.md updated successfully.")

    # --check 모드: CI에서 차이가 있으면 실패
    if '--check' in sys.argv:
        if INDEX_PATH.exists():
            existing = Path(str(INDEX_PATH) + '.bak').read_text(encoding='utf-8') if Path(str(INDEX_PATH) + '.bak').exists() else ''
            if existing != index_content:
                print("ERROR: index.md is out of sync with README.md!", file=sys.stderr)
                print("Run 'python scripts/sync-toc.py' to fix.", file=sys.stderr)
                sys.exit(1)


if __name__ == '__main__':
    main()
