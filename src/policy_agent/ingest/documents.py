"""Parse MOM HTML pages and synthetic memos into section-aware blocks."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup, Tag

_WS = re.compile(r"\s+")


def clean(text: str) -> str:
    text = _WS.sub(" ", text.replace("\xa0", " ")).strip()
    text = re.sub(r"\s+([.,;:%])", r"\1", text)
    return re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))


@dataclass
class Block:
    kind: str  # heading | para | table
    text: str
    section: str = ""


@dataclass
class Document:
    source_id: str
    title: str
    pub_date: str
    blocks: list[Block] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks)

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()


_H, _E = "\u2983", "\u2984"  # private markers wrapped around candidate heading text
_BLOCK = ["p", "li", "h2", "h3", "h4", "tr", "div", "ol", "ul"]
_DROP_CLASSES = ("module-share", "share-widget", "article-meta")


def _table_text(t: Tag) -> str:
    rows = [" | ".join(clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])) for tr in t.find_all("tr")]
    return "\n".join(r for r in rows if r.strip(" |"))


def _heading_like(text: str) -> bool:
    return 0 < len(text) <= 80 and not text.endswith((".", "?", ":", ";", ","))


def parse_mom_html(raw_html: str, source_id: str) -> Document:
    """MOM pages mix <p> markup with plain text split by <br>; both are flattened to paragraphs."""
    soup = BeautifulSoup(raw_html, "lxml")
    root = soup.select_one("div.page-content") or soup.select_one("div.main-content")
    if root is None:
        raise ValueError(f"{source_id}: no article container")
    time = root.find("time")
    if not isinstance(time, Tag):
        raise ValueError(f"{source_id}: no publication date")
    stamp = str(time.get("datetime") or time.get_text()).strip()
    pub = datetime.strptime(stamp, "%d-%m-%Y").date().isoformat()
    h1 = root.find("h1")
    title = clean(h1.get_text(" ")) if isinstance(h1, Tag) else source_id
    for t in root.find_all(["script", "style", "sup", "noscript", "h1"]):
        t.decompose()
    for t in root.find_all(class_=lambda c: c and any(d in c for d in _DROP_CLASSES)):
        t.decompose()
    for node in root.find_all(string=lambda x: bool(x) and x.strip().startswith("Last Updated")):
        if node.parent is not None and node.parent is not root:
            node.parent.decompose()

    tables: list[str] = []
    for t in root.find_all("table"):
        tables.append(_table_text(t))
        t.replace_with(f"\n\n@@TABLE{len(tables) - 1}@@\n\n")
    for t in root.find_all(["h2", "h3", "h4", "strong", "b"]):
        text = clean(t.get_text(" "))
        if _heading_like(text) or t.name in ("h2", "h3", "h4"):
            t.string = f"{_H}{text}{_E}"
    for t in root.find_all("br"):
        t.replace_with("\n")
    for t in root.find_all(_BLOCK):
        t.insert_before("\n\n")
        t.insert_after("\n\n")

    doc = Document(source_id=source_id, title=title, pub_date=pub)
    section = "Summary"
    for line in re.split(r"\n+", root.get_text()):
        marked = clean(line)
        text = clean(marked.replace(_H, "").replace(_E, ""))
        if not text or text == title:
            continue
        if m := re.fullmatch(r"@@TABLE(\d+)@@", text):
            doc.blocks.append(Block("table", tables[int(m.group(1))], section))
            continue
        whole = marked.startswith(_H) and marked.endswith(_E) and marked.count(_H) == 1
        if (whole or text.isupper()) and _heading_like(text):
            section = text.title() if text.isupper() else text
            doc.blocks.append(Block("heading", section, section))
        else:
            doc.blocks.append(Block("para", text, section))
    return doc


def extraction_coverage(raw_html: str, doc: Document) -> float:
    """Extracted characters / characters in a naive text pull of the article container.

    A low ratio means body text was lost (e.g. a layout the parser does not handle).
    """
    soup = BeautifulSoup(raw_html, "lxml")
    root = soup.select_one("div.page-content") or soup.select_one("div.main-content")
    if root is None:
        raise ValueError("no article container")
    for t in root.find_all(["script", "style", "sup", "noscript", "h1"]):
        t.decompose()
    for t in root.find_all(class_=lambda c: c and any(d in c for d in _DROP_CLASSES)):
        t.decompose()
    naive = len(re.sub(r"\s+", "", root.get_text()))
    got = len(re.sub(r"\s+", "", doc.text))
    return got / naive if naive else 0.0


def parse_memo(md: str, source_id: str) -> Document:
    m = re.match(r"---\n(.*?)\n---\n(.*)", md, re.S)
    if not m:
        raise ValueError(f"{source_id}: missing front matter")
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    doc = Document(source_id=meta["source_id"], title=meta["title"], pub_date=meta["pub_date"], meta=meta)
    section = "Summary"
    for chunk in re.split(r"\n\s*\n", m.group(2).strip()):
        chunk = chunk.strip()
        if not chunk or chunk.startswith("> **SYNTHETIC DOCUMENT"):
            continue  # banner is carried as metadata (synthetic=true), not as text
        if chunk.startswith("# "):
            section = chunk[2:].strip()
            continue
        doc.blocks.append(Block("table" if chunk.startswith("|") else "para", chunk, section))
    return doc
