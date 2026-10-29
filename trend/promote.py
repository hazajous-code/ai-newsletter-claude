"""예약 발행: trend/scheduled.json 에 등록된 호를 발행일(KST)이 되면 메인으로 올린다.

- issues/<id>.html            → index.html   (주간 뉴스레터)
- issues/<id>-marketer.html   → marketer.html (마케터 자료)
- archive.html 의 <!-- ARCHIVE:START --> 아래에 한 줄 추가
- 처리한 항목은 scheduled.json 에 "promoted": true 로 표시 (여러 번 실행해도 안전)

매일 아침 daily.yml 이 실행하고, 목요일 주간 발행 작업도 먼저 실행한다.
"""
import datetime as dt
import json
import pathlib
import re
import sys

T = pathlib.Path(__file__).resolve().parent
KST = dt.timezone(dt.timedelta(hours=9))


def to_root(html: str, iid: str) -> str:
    html = html.replace('href="../', 'href="')
    html = html.replace('src="../', 'src="')
    html = html.replace(f'href="{iid}-marketer.html"', 'href="marketer.html"')
    html = html.replace(f'href="{iid}.html"', 'href="index.html"')
    return html


def main(today: str | None = None) -> int:
    today = today or dt.datetime.now(KST).strftime("%Y-%m-%d")
    path = T / "scheduled.json"
    if not path.exists():
        print("scheduled.json 없음")
        return 0
    items = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for it in sorted(items, key=lambda x: x["date"]):
        if it.get("promoted") or it["date"] > today:
            continue
        iid = it["id"]
        nl = (T / "issues" / f"{iid}.html").read_text(encoding="utf-8")
        mk = (T / "issues" / f"{iid}-marketer.html").read_text(encoding="utf-8")
        (T / "index.html").write_text(to_root(nl, iid), encoding="utf-8")
        (T / "marketer.html").write_text(to_root(mk, iid), encoding="utf-8")
        ar = (T / "archive.html").read_text(encoding="utf-8")
        if f'issues/{iid}.html' not in ar:
            line = (f'  <li><time>{it["date"].replace("-", ".")}</time><span><a href="issues/{iid}.html">{it["title"]}</a>'
                    f' · <a href="issues/{iid}-marketer.html" class="muted">마케터 자료</a></span></li>')
            ar = ar.replace("<!-- ARCHIVE:START -->", "<!-- ARCHIVE:START -->\n" + line, 1)
            (T / "archive.html").write_text(ar, encoding="utf-8")
        it["promoted"] = True
        it["promoted_at"] = dt.datetime.now(KST).isoformat(timespec="minutes")
        changed = True
        print(f"발행: {iid} — {it['title']}")
    if changed:
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        print(f"오늘({today}) 발행할 예약 호 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
