#!/usr/bin/env python3
"""
CS Knowledge Base → Tistory 자동 포스팅 스크립트 (SEO 최적화 포함)

사용법:
  # 변환만 (output/ 디렉토리에 저장)
  python scripts/tistory-convert.py network/websocket-deep-dive.md
  python scripts/tistory-convert.py --all

  # Tistory API로 자동 게시
  python scripts/tistory-convert.py --publish network/websocket-deep-dive.md
  python scripts/tistory-convert.py --publish --all

  # 파일 목록 확인
  python scripts/tistory-convert.py --list

사전 준비 (Tistory API 사용 시):
  1. https://www.tistory.com/guide/api/manage/register 에서 앱 등록
  2. .env 파일에 아래 내용 작성:
     TISTORY_ACCESS_TOKEN=your_access_token
     TISTORY_BLOG_NAME=your-blog-name
"""

import os
import re
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

# 카테고리별 태그 매핑
CATEGORY_TAGS = {
    "java-jvm": ["Java", "JVM", "백엔드", "CS지식"],
    "spring": ["Spring", "Spring Boot", "백엔드", "CS지식"],
    "network": ["네트워크", "Network", "CS지식", "백엔드"],
    "os": ["운영체제", "OS", "CS지식"],
    "database": ["데이터베이스", "DB", "SQL", "CS지식"],
    "data-structure": ["자료구조", "알고리즘", "CS지식"],
    "design-pattern": ["디자인패턴", "아키텍처", "CS지식"],
}

# 키워드 기반 추가 태그
KEYWORD_TAGS = {
    "websocket": ["WebSocket", "실시간통신"],
    "http": ["HTTP", "HTTPS"],
    "tcp": ["TCP", "프로토콜"],
    "jvm": ["JVM", "가비지컬렉션"],
    "memory": ["메모리", "GC"],
    "load-balancer": ["로드밸런서", "인프라"],
    "vpn": ["VPN", "보안"],
    "gc": ["GC", "가비지컬렉션"],
    "spring": ["Spring", "IoC", "DI"],
    "thread": ["스레드", "동시성"],
    "process": ["프로세스"],
    "index": ["인덱스", "쿼리최적화"],
    "transaction": ["트랜잭션", "ACID"],
}


def load_env():
    """프로젝트 루트의 .env 파일에서 환경변수 로드."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return {}
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def find_md_files():
    """변환 가능한 마크다운 파일 목록 반환."""
    files = []
    for category_dir in sorted(REPO_ROOT.iterdir()):
        if not category_dir.is_dir():
            continue
        if category_dir.name.startswith(".") or category_dir.name in ("scripts", "output"):
            continue
        for md in sorted(category_dir.glob("*.md")):
            files.append(md.relative_to(REPO_ROOT))
    return files


def extract_title(content):
    """첫 번째 # 헤딩에서 제목 추출."""
    match = re.match(r"^#\s+(.+)", content)
    return match.group(1).strip() if match else "제목 없음"


def extract_description(content, max_len=160):
    """핵심 정리 섹션의 첫 문단 → 메타 디스크립션."""
    lines = content.split("\n")
    capture = False
    desc_lines = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        if "핵심 정리" in stripped:
            capture = True
            continue

        if capture:
            if stripped.startswith("## ") and desc_lines:
                break
            if stripped.startswith("### ") or not stripped:
                if desc_lines:
                    break
                continue
            desc_lines.append(stripped)

    desc = " ".join(desc_lines)
    # 마크다운 문법 제거
    desc = re.sub(r"\*\*(.+?)\*\*", r"\1", desc)
    desc = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", desc)
    desc = re.sub(r"`(.+?)`", r"\1", desc)

    if len(desc) > max_len:
        desc = desc[: max_len - 3] + "..."
    return desc


def extract_tags(filepath, content):
    """카테고리 + 파일명 키워드 기반 태그 자동 추출."""
    category = filepath.parts[0] if len(filepath.parts) > 1 else ""
    tags = list(CATEGORY_TAGS.get(str(category), ["CS지식"]))

    # 파일명 기반으로만 키워드 태그 추출 (본문 매칭은 노이즈가 많음)
    filename = filepath.stem.lower()
    for keyword, extra_tags in KEYWORD_TAGS.items():
        if keyword in filename:
            for t in extra_tags:
                if t not in tags:
                    tags.append(t)

    # 제목에서 추가 키워드 추출
    title = extract_title(content).lower()
    for keyword, extra_tags in KEYWORD_TAGS.items():
        if keyword in title:
            for t in extra_tags:
                if t not in tags:
                    tags.append(t)

    return tags


def add_seo_header(content, title, description):
    """본문 상단에 SEO 친화적 요약 블록 추가."""
    seo_block = (
        f"<!-- SEO -->\n"
        f"<!-- title: {title} -->\n"
        f"<!-- description: {description} -->\n"
        f"<!-- /SEO -->\n\n"
    )
    return seo_block + content


def convert_file(filepath):
    """마크다운 파일을 Tistory 포스팅용으로 변환."""
    full_path = REPO_ROOT / filepath
    content = full_path.read_text(encoding="utf-8")

    title = extract_title(content)
    description = extract_description(content)
    tags = extract_tags(filepath, content)
    category = str(filepath.parts[0]) if len(filepath.parts) > 1 else "기타"

    # SEO 메타 주석 + 원본 마크다운
    body = add_seo_header(content, title, description)

    # 시리즈 푸터
    footer = (
        f"\n\n---\n"
        f"> 이 글은 **CS Knowledge Base** 시리즈의 [{category}] 편입니다.\n"
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_name = filepath.stem

    # 포스팅용 마크다운
    post_path = OUTPUT_DIR / f"{out_name}.md"
    post_path.write_text(body + footer, encoding="utf-8")

    # SEO 메타 정보 JSON
    meta = {
        "title": title,
        "description": description,
        "tags": tags,
        "category": category,
        "source_file": str(filepath),
    }
    meta_path = OUTPUT_DIR / f"{out_name}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return meta, post_path, meta_path


# ─── Tistory API ───────────────────────────────────────────


class TistoryAPI:
    """Tistory Open API 클라이언트."""

    BASE_URL = "https://www.tistory.com/apis"

    def __init__(self, access_token, blog_name):
        self.access_token = access_token
        self.blog_name = blog_name

    def _request(self, endpoint, params):
        """Tistory API 호출."""
        params["access_token"] = self.access_token
        params["output"] = "json"
        params["blogName"] = self.blog_name

        url = f"{self.BASE_URL}/{endpoint}"
        data = urllib.parse.urlencode(params).encode("utf-8")

        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"  API 오류 ({e.code}): {error_body}")
            return None

    def list_categories(self):
        """블로그 카테고리 목록 조회."""
        result = self._request("category/list", {})
        if result and "tistory" in result:
            return result["tistory"]["item"]["categories"]
        return []

    def publish(self, title, content, tags, category_id="0", visibility=3):
        """
        글 발행.

        visibility: 0=비공개, 1=보호, 2=발행예약, 3=공개
        """
        params = {
            "title": title,
            "content": content,
            "tag": ",".join(tags),
            "category": category_id,
            "visibility": str(visibility),
        }
        result = self._request("post/write", params)
        if result and "tistory" in result:
            return result["tistory"]
        return None


def publish_to_tistory(meta, post_path):
    """변환된 파일을 Tistory에 게시."""
    env = load_env()
    token = env.get("TISTORY_ACCESS_TOKEN") or os.environ.get("TISTORY_ACCESS_TOKEN")
    blog = env.get("TISTORY_BLOG_NAME") or os.environ.get("TISTORY_BLOG_NAME")

    if not token or not blog:
        print("\n  .env 파일에 아래 값을 설정해주세요:")
        print("    TISTORY_ACCESS_TOKEN=your_token")
        print("    TISTORY_BLOG_NAME=your-blog-name")
        print("\n  토큰 발급: https://www.tistory.com/guide/api/manage/register")
        return None

    api = TistoryAPI(token, blog)
    content = post_path.read_text(encoding="utf-8")

    result = api.publish(
        title=meta["title"],
        content=content,
        tags=meta["tags"],
    )

    if result:
        post_url = result.get("url", "")
        post_id = result.get("postId", "")
        print(f"  발행 완료! ID: {post_id}")
        if post_url:
            print(f"  URL: {post_url}")
        return result

    print("  발행 실패. 토큰과 블로그명을 확인해주세요.")
    return None


# ─── CLI ───────────────────────────────────────────────────


def print_result(meta, post_path, meta_path):
    """변환 결과 출력."""
    print(f"  제목: {meta['title']}")
    print(f"  설명: {meta['description'][:80]}...")
    print(f"  태그: {', '.join(meta['tags'])}")
    print(f"  본문: {post_path}")
    print(f"  메타: {meta_path}")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = sys.argv[1:]
    publish = "--publish" in args
    all_files = "--all" in args
    list_files = "--list" in args
    file_args = [a for a in args if not a.startswith("--")]

    if list_files:
        files = find_md_files()
        print(f"\n변환 가능한 파일 ({len(files)}개):\n")
        for f in files:
            print(f"  {f}")
        print()
        return

    if all_files:
        files = find_md_files()
    elif file_args:
        files = [Path(f) for f in file_args]
    else:
        print(__doc__)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Tistory 포스팅 {'게시' if publish else '변환'}기")
    print(f"{'='*60}\n")

    results = []
    for filepath in files:
        full_path = REPO_ROOT / filepath
        if not full_path.exists():
            print(f"  파일 없음: {filepath}\n")
            continue

        print(f"[{filepath}]")
        meta, post_path, meta_path = convert_file(filepath)
        print_result(meta, post_path, meta_path)
        results.append((meta, post_path, meta_path))

    if publish and results:
        print(f"{'='*60}")
        print("  Tistory API 게시 시작")
        print(f"{'='*60}\n")

        for meta, post_path, _ in results:
            print(f"[게시] {meta['title']}")
            publish_to_tistory(meta, post_path)
            print()

    print(f"{'='*60}")
    if not publish:
        print("  변환 완료! Tistory에 자동 게시하려면:")
        print("  python scripts/tistory-convert.py --publish --all")
        print()
    print("  SEO 체크리스트:")
    print("    - 제목에 핵심 키워드 포함")
    print("    - Tistory 글 설정에서 '검색 허용' 체크")
    print("    - 태그 5개 이상 등록")
    print("    - 대표 이미지(썸네일) 설정")
    print("    - Google Search Console에 사이트맵 등록")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
