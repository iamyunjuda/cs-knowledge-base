#!/usr/bin/env python3
"""
마크다운 파일을 티스토리 붙여넣기용 HTML로 변환하는 스크립트.
기본적으로 output/ 폴더에 같은 이름의 .html 파일로 저장됩니다.

사용법:
  python scripts/to-html.py topics/network/http-tcp-relationship.md
    → output/http-tcp-relationship.html 저장

  python scripts/to-html.py topics/network/http-tcp-relationship.md -o custom.html
    → 지정 경로에 저장

  python scripts/to-html.py topics/network/http-tcp-relationship.md --open
    → 브라우저에서 미리보기
"""

import argparse
import sys
import webbrowser
import tempfile
from pathlib import Path

import markdown

REPO_ROOT = Path(__file__).resolve().parent.parent

# 티스토리 에디터에서 잘 보이는 인라인 스타일
STYLE = """\
<style>
  .tistory-content { font-family: 'Pretendard', -apple-system, sans-serif; line-height: 1.8; color: #333; max-width: 800px; }
  .tistory-content h1 { font-size: 1.8em; border-bottom: 2px solid #333; padding-bottom: 8px; margin-top: 32px; }
  .tistory-content h2 { font-size: 1.4em; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin-top: 28px; }
  .tistory-content h3 { font-size: 1.2em; margin-top: 24px; }
  .tistory-content code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
  .tistory-content pre { background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 8px; overflow-x: auto; }
  .tistory-content pre code { background: none; color: inherit; padding: 0; }
  .tistory-content blockquote { border-left: 4px solid #3b82f6; background: #eff6ff; padding: 12px 16px; margin: 16px 0; border-radius: 0 8px 8px 0; }
  .tistory-content table { border-collapse: collapse; width: 100%; margin: 16px 0; }
  .tistory-content th, .tistory-content td { border: 1px solid #ddd; padding: 10px 12px; text-align: left; }
  .tistory-content th { background: #f8f9fa; font-weight: 600; }
  .tistory-content img { max-width: 100%; border-radius: 8px; }
  .tistory-content hr { border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }
  .tistory-content ul, .tistory-content ol { padding-left: 24px; }
  .tistory-content li { margin-bottom: 4px; }
</style>"""

PREVIEW_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} - 미리보기</title>
  {style}
</head>
<body style="display:flex;justify-content:center;padding:40px 20px;background:#fafafa;">
  <div class="tistory-content">
{body}
  </div>
</body>
</html>"""


def convert(md_path: Path) -> tuple[str, str]:
    """마크다운 파일을 HTML로 변환. (제목, HTML body) 반환."""
    text = md_path.read_text(encoding="utf-8")

    # Jekyll front matter 제거 (--- ... ---)
    import re
    text = re.sub(r'^---\s*\n.*?\n---\s*\n', '', text, count=1, flags=re.DOTALL)

    # 첫 번째 # 제목 추출
    title = md_path.stem
    for line in text.splitlines():
        if line.startswith("# "):
            title = line.lstrip("# ").strip()
            break

    extensions = [
        "fenced_code",
        "codehilite",
        "tables",
        "toc",
        "nl2br",
        "sane_lists",
    ]
    extension_configs = {
        "codehilite": {"css_class": "highlight", "guess_lang": False},
    }

    html_body = markdown.markdown(
        text,
        extensions=extensions,
        extension_configs=extension_configs,
    )

    return title, html_body


def main():
    parser = argparse.ArgumentParser(description="마크다운 → 티스토리 HTML 변환")
    parser.add_argument("file", help="변환할 마크다운 파일 경로")
    parser.add_argument("-o", "--output", help="HTML 출력 파일 경로 (미지정 시 output/ 폴더에 자동 저장)")
    parser.add_argument("--open", action="store_true", help="브라우저에서 미리보기")
    parser.add_argument("--full", action="store_true", help="style 태그 포함 전체 HTML 출력")
    parser.add_argument("--stdout", action="store_true", help="파일 저장 대신 stdout으로 출력")
    args = parser.parse_args()

    md_path = Path(args.file)
    if not md_path.is_absolute():
        md_path = REPO_ROOT / md_path

    if not md_path.exists():
        print(f"ERROR: {md_path} 파일을 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    title, html_body = convert(md_path)

    # 티스토리 붙여넣기용: div로 감싸기
    tistory_html = f'<div class="tistory-content">\n{html_body}\n</div>'
    if args.full:
        tistory_html = f'{STYLE}\n{tistory_html}'

    if args.open:
        # 브라우저 미리보기
        preview = PREVIEW_TEMPLATE.format(title=title, style=STYLE, body=html_body)
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        tmp.write(preview)
        tmp.close()
        webbrowser.open(f"file://{tmp.name}")
        print(f"미리보기: {tmp.name}")

    if args.stdout:
        print(tistory_html)
    elif not args.open:
        # 기본: output/ 폴더에 자동 저장
        if args.output:
            out_path = Path(args.output)
        else:
            out_dir = REPO_ROOT / "output"
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / f"{md_path.stem}.html"
        out_path.write_text(tistory_html, encoding="utf-8")
        print(f"저장 완료: {out_path}")


if __name__ == "__main__":
    main()
