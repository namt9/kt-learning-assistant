"""Xuất ontology OWL 2 (RDF/XML) từ knowledge/*.yaml để mở bằng Protégé.

YAML vẫn là nguồn sự thật duy nhất: ontology được SINH ra, không sửa tay, nên luôn khớp với KG
trong Neo4j (cùng nút, cùng quan hệ, cùng tên quan hệ ở dạng camelCase).

python -m backend.app.kg.owl                    # -> knowledge/ontology/c_tutor.owl
python -m backend.app.kg.owl --with-logs        # kèm log nộp bài (Student, StudentCode, exhibits)

Cấu trúc:

- TBox: lớp Concept, ConceptGroup, BugPattern, PedagogicalAction (6 lớp con theo type), Problem,
  Student, StudentCode, LearningStyle, DetectionTool, MinedRule (AddRule / SuppressRule); thuộc
  tính đối tượng có domain/range, cặp nghịch đảo, prerequisiteOf bắc cầu.
- Lớp định nghĩa (reasoner tự phân loại): MemoryBug, PointerBug, BeginnerConcept,
  VisualAction, VerbalAction, ActiveAction, ReflectiveAction, RemediableBug.
- ABox: mọi khái niệm, mẫu lỗi, hành động, bài tập, luật khai phá (và log nộp bài nếu yêu cầu).
"""

from __future__ import annotations

import argparse
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from ..config import ROOT, load_settings
from .model import KnowledgeBase

BASE = "http://www.semanticweb.org/cs2307/ontologies/c-tutor"
NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

ACTION_CLASSES = {
    "GIAI_THICH": ("Explanation", "Giải thích"),
    "VI_DU": ("WorkedExample", "Ví dụ mẫu"),
    "TRUC_QUAN": ("Visualization", "Trực quan hoá"),
    "GO_LOI": ("DebuggingExercise", "Bài tập gỡ lỗi"),
    "BAI_TAP": ("Exercise", "Bài tập luyện tập"),
    "CAU_HOI": ("Quiz", "Câu hỏi kiểm tra"),
}
STYLE_LABELS = {
    "visual": "Trực quan (visual)",
    "verbal": "Lời nói / chữ (verbal)",
    "active": "Chủ động (active)",
    "reflective": "Suy ngẫm (reflective)",
}
TOOL_LABELS = {
    "gcc": "gcc -Wall -Wextra",
    "cppcheck": "cppcheck (phân tích tĩnh)",
    "asan": "AddressSanitizer",
    "ubsan": "UndefinedBehaviorSanitizer",
    "custom_rule": "Luật tự viết (v0)",
    "judge": "Bộ chấm (kết quả test)",
}

CLASSES = {
    # id: (nhãn tiếng Việt, lớp cha, chú thích)
    "Concept": ("Khái niệm", None, "Khái niệm lập trình C/C++ trong Concept Map."),
    "ConceptGroup": ("Cụm khái niệm", None, "Biến, Con trỏ, CTDL, Quản lý bộ nhớ, Nền tảng."),
    "BugPattern": ("Mẫu lỗi", None, "Loại lỗi sinh viên hay mắc (Bug_Pattern)."),
    "PedagogicalAction": ("Hành động sư phạm", None, "Cách khắc phục, dạy lại."),
    "Problem": ("Bài tập", None, "Bài tập lập trình có test case."),
    "Student": ("Sinh viên", None, None),
    "StudentCode": ("Bài nộp", None, "Một lần nộp code của sinh viên (Student_Code)."),
    "LearningStyle": ("Phong cách học", None, "Felder–Silverman rút gọn 2 chiều."),
    "DetectionTool": ("Công cụ phát hiện", None, "Công cụ phát hiện mẫu lỗi."),
    "MinedRule": ("Luật khai phá", None, "Luật kết hợp khai phá bằng Apriori từ log nộp bài."),
    "AddRule": ("Luật bổ sung lỗi", "MinedRule", "Khi điều kiện đúng, dự đoán thêm một mẫu lỗi."),
    "SuppressRule": ("Luật khử nhiễu", "MinedRule", "Cảnh báo là hệ quả của lỗi khác nên bỏ qua."),
    **{
        cls: (label, "PedagogicalAction", f"Hành động sư phạm loại {code}.")
        for code, (cls, label) in ACTION_CLASSES.items()
    },
}
TOP_CLASSES = [c for c, (_, parent, _) in CLASSES.items() if parent is None]

OBJECT_PROPERTIES = {
    # id: (nhãn, domain, range, nghịch đảo, đặc tính)
    "submitted": ("đã nộp", "Student", "StudentCode", "submittedBy", ()),
    "forProblem": ("cho bài", "StudentCode", "Problem", None, ("Functional",)),
    "exhibits": ("thể hiện lỗi", "StudentCode", "BugPattern", "exhibitedBy", ()),
    "remediatedBy": ("khắc phục bằng", "BugPattern", "PedagogicalAction", "remediates", ()),
    "relatedTo": ("liên quan khái niệm", "BugPattern", "Concept", "hasRelatedBug", ()),
    "teaches": ("dạy", "PedagogicalAction", "Concept", "taughtBy", ()),
    "usesProblem": ("dùng bài tập", "PedagogicalAction", "Problem", None, ()),
    "practices": ("luyện khái niệm", "Problem", "Concept", None, ()),
    "prerequisiteOf": (
        "là tiên quyết của", "Concept", "Concept", "hasPrerequisite", ("Transitive",)
    ),
    "partOf": ("thuộc cụm", "Concept", "ConceptGroup", "hasMember", ("Functional",)),
    "suitsStyle": ("hợp phong cách", "PedagogicalAction", "LearningStyle", None, ()),
    "detectedBy": ("phát hiện bởi", "BugPattern", "DetectionTool", None, ()),
    "ifFound": ("khi công cụ báo", "MinedRule", "BugPattern", None, ()),
    "concludes": ("kết luận về", "MinedRule", "BugPattern", None, ("Functional",)),
}  # fmt: skip
INVERSE_LABELS = {
    "submittedBy": "được nộp bởi",
    "exhibitedBy": "xuất hiện trong",
    "remediates": "khắc phục",
    "hasRelatedBug": "có lỗi liên quan",
    "taughtBy": "được dạy bởi",
    "hasPrerequisite": "cần học trước",
    "hasMember": "gồm khái niệm",
}

DATA_PROPERTIES = {
    # id: (nhãn, domain hoặc None, kiểu xsd)
    "identifier": ("mã", None, "string"),
    "level": ("mức độ (1–3)", None, "integer"),
    "description": ("mô tả", "Concept", "string"),
    "hint": ("gợi ý v0", "BugPattern", "string"),
    "content": ("nội dung", "PedagogicalAction", "string"),
    "verdict": ("kết quả chấm", "StudentCode", "string"),
    "score": ("điểm", "StudentCode", "decimal"),
    "submittedAt": ("thời điểm nộp", "StudentCode", "dateTime"),
    "condition": ("điều kiện khác", "MinedRule", "string"),
    "support": ("độ hỗ trợ", "MinedRule", "decimal"),
    "confidence": ("độ tin cậy", "MinedRule", "decimal"),
    "lift": ("lift", "MinedRule", "decimal"),
}  # fmt: skip


def _iri(name: str) -> str:
    return f"{BASE}#{name}"


class _Writer:
    def __init__(self) -> None:
        for p, uri in NS.items():
            ET.register_namespace(p, uri)
        ET.register_namespace("ct", BASE + "#")
        self.root = ET.Element(
            self.q("rdf", "RDF"), {"{http://www.w3.org/XML/1998/namespace}base": BASE}
        )
        self.individuals: set[str] = set()

    @staticmethod
    def q(prefix: str, tag: str) -> str:
        return f"{{{NS[prefix]}}}{tag}"

    def el(self, parent: ET.Element, prefix: str, tag: str, **attrs) -> ET.Element:
        e = ET.SubElement(parent, self.q(prefix, tag))
        for k, v in attrs.items():
            p, _, local = k.partition("_")
            e.set(self.q(p, local), v)
        return e

    def ref(self, parent, prefix, tag, target: str) -> ET.Element:
        return self.el(parent, prefix, tag, rdf_resource=target)

    def label(self, e: ET.Element, text: str, tag: str = "label") -> None:
        if text:
            lab = self.el(e, "rdfs", tag)
            lab.set(XML_LANG, "vi")
            lab.text = text

    def literal(self, e, name: str, value, xsd: str) -> None:
        if value is None or value == "":
            return
        d = ET.SubElement(e, f"{{{BASE}#}}{name}")
        d.set(self.q("rdf", "datatype"), NS["xsd"] + xsd)
        d.text = str(value)

    def individual(self, name: str, cls: str, label: str = "", ident: str | None = None):
        if name in self.individuals:
            raise ValueError(f"trùng IRI cá thể: {name}")
        self.individuals.add(name)
        e = self.el(self.root, "owl", "NamedIndividual", rdf_about=_iri(name))
        self.ref(e, "rdf", "type", _iri(cls))
        self.label(e, label)
        self.literal(e, "identifier", ident or name, "string")
        return e

    def link(self, e, prop: str, target: str) -> None:
        ET.SubElement(e, f"{{{BASE}#}}{prop}").set(self.q("rdf", "resource"), _iri(target))


def _tbox(w: _Writer) -> None:
    onto = w.el(w.root, "owl", "Ontology", rdf_about=BASE)
    w.label(onto, "Ontology trợ lý học lập trình C/C++ (Multi-Agent + Knowledge Graph)")
    w.label(onto, "Sinh tự động từ knowledge/*.yaml bởi backend/app/kg/owl.py, không sửa tay.",
            "comment")  # fmt: skip

    for cls, (label, parent, comment) in CLASSES.items():
        e = w.el(w.root, "owl", "Class", rdf_about=_iri(cls))
        w.label(e, label)
        w.label(e, comment or "", "comment")
        if parent:
            w.ref(e, "rdfs", "subClassOf", _iri(parent))

    disjoint = w.el(w.root, "owl", "AllDisjointClasses")
    members = w.el(disjoint, "owl", "members", rdf_parseType="Collection")
    for cls in TOP_CLASSES:
        w.el(members, "owl", "Class", rdf_about=_iri(cls))
    disjoint = w.el(w.root, "owl", "AllDisjointClasses")
    members = w.el(disjoint, "owl", "members", rdf_parseType="Collection")
    for cls, _ in ACTION_CLASSES.values():
        w.el(members, "owl", "Class", rdf_about=_iri(cls))

    for prop, (label, dom, rng, inverse, traits) in OBJECT_PROPERTIES.items():
        e = w.el(w.root, "owl", "ObjectProperty", rdf_about=_iri(prop))
        w.label(e, label)
        w.ref(e, "rdfs", "domain", _iri(dom))
        w.ref(e, "rdfs", "range", _iri(rng))
        for t in traits:
            w.ref(e, "rdf", "type", NS["owl"] + f"{t}Property")
        if inverse:
            inv = w.el(w.root, "owl", "ObjectProperty", rdf_about=_iri(inverse))
            w.label(inv, INVERSE_LABELS[inverse])
            w.ref(inv, "owl", "inverseOf", _iri(prop))
            if "Transitive" in traits:
                w.ref(inv, "rdf", "type", NS["owl"] + "TransitiveProperty")

    for prop, (label, dom, xsd) in DATA_PROPERTIES.items():
        e = w.el(w.root, "owl", "DatatypeProperty", rdf_about=_iri(prop))
        w.label(e, label)
        if dom:
            w.ref(e, "rdfs", "domain", _iri(dom))
        w.ref(e, "rdfs", "range", NS["xsd"] + xsd)


def _defined_classes(w: _Writer) -> None:
    """Lớp định nghĩa bằng điều kiện cần và đủ: reasoner (HermiT) tự xếp cá thể vào."""

    def defined(name: str, label: str, comment: str, base: str, restriction) -> None:
        e = w.el(w.root, "owl", "Class", rdf_about=_iri(name))
        w.label(e, label)
        w.label(e, comment, "comment")
        w.ref(e, "rdfs", "subClassOf", _iri(base))
        eq = w.el(e, "owl", "equivalentClass")
        inter = w.el(eq, "owl", "Class")
        lst = w.el(inter, "owl", "intersectionOf", rdf_parseType="Collection")
        w.el(lst, "owl", "Class", rdf_about=_iri(base))
        restriction(lst)

    def some(prop: str, filler):
        def build(parent):
            r = w.el(parent, "owl", "Restriction")
            w.ref(r, "owl", "onProperty", _iri(prop))
            if isinstance(filler, str):
                w.ref(r, "owl", "someValuesFrom", _iri(filler))
            else:
                f = w.el(r, "owl", "someValuesFrom")
                filler(f)
            return r

        return build

    def has_value(prop: str, individual: str):
        def build(parent):
            r = w.el(parent, "owl", "Restriction")
            w.ref(r, "owl", "onProperty", _iri(prop))
            w.ref(r, "owl", "hasValue", _iri(individual))
            return r

        return build

    def has_literal(prop: str, value: str, xsd: str):
        def build(parent):
            r = w.el(parent, "owl", "Restriction")
            w.ref(r, "owl", "onProperty", _iri(prop))
            v = w.el(r, "owl", "hasValue")
            v.set(w.q("rdf", "datatype"), NS["xsd"] + xsd)
            v.text = value
            return r

        return build

    defined(
        "MemoryBug",
        "Lỗi quản lý bộ nhớ",
        "Mẫu lỗi liên quan tới ít nhất một khái niệm thuộc cụm Quản lý bộ nhớ.",
        "BugPattern",
        some("relatedTo", lambda f: has_value("partOf", "nhom_bo_nho")(f)),
    )
    defined(
        "PointerBug",
        "Lỗi con trỏ",
        "Mẫu lỗi liên quan tới ít nhất một khái niệm thuộc cụm Con trỏ.",
        "BugPattern",
        some("relatedTo", lambda f: has_value("partOf", "nhom_con_tro")(f)),
    )
    defined(
        "RemediableBug",
        "Lỗi có cách khắc phục",
        "Mẫu lỗi có ít nhất một hành động sư phạm khắc phục.",
        "BugPattern",
        some("remediatedBy", "PedagogicalAction"),
    )
    defined(
        "BeginnerConcept",
        "Khái niệm cơ bản",
        "Khái niệm có level = 1.",
        "Concept",
        has_literal("level", "1", "integer"),
    )
    for style in STYLE_LABELS:
        defined(f"{style.capitalize()}Action", f"Hành động hợp người học {style}",
                f"Hành động sư phạm phù hợp phong cách {style}.",
                "PedagogicalAction", has_value("suitsStyle", f"style_{style}"))  # fmt: skip


def _abox(w: _Writer, kb: KnowledgeBase, mined: list[dict]) -> None:
    for s, label in STYLE_LABELS.items():
        w.individual(f"style_{s}", "LearningStyle", label, s)
    for t, label in TOOL_LABELS.items():
        w.individual(f"tool_{t}", "DetectionTool", label, t)
    for g in kb.groups.values():
        w.individual(g.id, "ConceptGroup", g.name)
    for c in kb.concepts.values():
        e = w.individual(c.id, "Concept", c.name)
        w.literal(e, "level", c.level, "integer")
        w.literal(e, "description", c.description, "string")
        w.link(e, "partOf", c.group)
        for p in c.prerequisites:
            w.link(e, "hasPrerequisite", p)
    for p in kb.problems.values():
        e = w.individual(p.id, "Problem", p.title)
        for c in p.concepts:
            w.link(e, "practices", c)
    remediated_by: dict[str, list[str]] = {}
    for a in kb.actions.values():
        cls = ACTION_CLASSES[a.type][0]
        e = w.individual(a.id, cls, a.title)
        w.literal(e, "level", a.level, "integer")
        w.literal(e, "content", a.content, "string")
        for c in a.teaches:
            w.link(e, "teaches", c)
        for s in a.styles:
            w.link(e, "suitsStyle", f"style_{s}")
        if a.problem:
            w.link(e, "usesProblem", a.problem)
        for b in a.remediates:
            remediated_by.setdefault(b, []).append(a.id)
    for b in kb.bug_patterns.values():
        e = w.individual(b.code, "BugPattern", b.name)
        w.literal(e, "hint", b.hint, "string")
        for c in b.concepts:
            w.link(e, "relatedTo", c)
        for t in b.detected_by:
            w.link(e, "detectedBy", f"tool_{t}")
        for a in remediated_by.get(b.code, []):
            w.link(e, "remediatedBy", a)
    for r in mined:
        cls = "SuppressRule" if r["kind"] == "suppress" else "AddRule"
        verb = "bỏ qua" if r["kind"] == "suppress" else "thêm"
        e = w.individual(r["id"], cls, f"{' ∧ '.join(r['if'])} → {verb} {r['then']}")
        others = [x for x in r["if"] if not x.startswith("found=")]
        for x in r["if"]:
            if x.startswith("found="):
                w.link(e, "ifFound", x.removeprefix("found="))
        w.link(e, "concludes", r["then"])
        w.literal(e, "condition", ", ".join(others), "string")
        for k in ("support", "confidence", "lift"):
            w.literal(e, k, r[k], "decimal")


def _logs(w: _Writer, kb: KnowledgeBase, db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        subs = [dict(r) for r in conn.execute(
            "SELECT id, student_id, problem_id, verdict, score, created_at FROM submissions"
        )]  # fmt: skip
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(findings)")}
        where = " WHERE suppressed_by IS NULL" if "suppressed_by" in cols else ""
        finds = conn.execute(
            "SELECT DISTINCT submission_id, bug_pattern FROM findings" + where
        ).fetchall()
    finally:
        conn.close()
    by_sub: dict = {}
    for f in finds:
        by_sub.setdefault(f["submission_id"], []).append(f["bug_pattern"])
    students: dict[str, ET.Element] = {}
    for s in subs:
        if s["student_id"] not in students:
            name = f"student_{s['student_id']}"
            students[s["student_id"]] = w.individual(
                name, "Student", s["student_id"], s["student_id"]
            )
        code = f"code_{s['id']}"
        e = w.individual(code, "StudentCode", f"Bài nộp {s['id']}", str(s["id"]))
        w.link(students[s["student_id"]], "submitted", code)
        if s["problem_id"] in kb.problems:
            w.link(e, "forProblem", s["problem_id"])
        w.literal(e, "verdict", s["verdict"], "string")
        w.literal(e, "score", s["score"], "decimal")
        if s["created_at"]:
            w.literal(e, "submittedAt", str(s["created_at"]).replace(" ", "T"), "dateTime")
        for b in sorted(set(by_sub.get(s["id"], []))):
            if b in kb.bug_patterns:
                w.link(e, "exhibits", b)
    return len(subs)


def build(kb: KnowledgeBase, mined: list[dict], db_path: Path | None = None) -> ET.ElementTree:
    w = _Writer()
    _tbox(w)
    _defined_classes(w)
    _abox(w, kb, mined)
    if db_path is not None:
        _logs(w, kb, db_path)
    tree = ET.ElementTree(w.root)
    ET.indent(tree)
    return tree


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "knowledge" / "ontology" / "c_tutor.owl")
    ap.add_argument("--with-logs", action="store_true", help="kèm log nộp bài từ SQLite")
    args = ap.parse_args(argv)
    settings = load_settings()
    kb = KnowledgeBase.load(ROOT / "knowledge", settings.problems_dir)
    report = kb.validate()
    if not report.ok:
        print("\n".join(report.errors))
        return 1
    rules_file = ROOT / "knowledge" / "mined_rules.yaml"
    mined = yaml.safe_load(rules_file.read_text(encoding="utf-8"))["rules"]
    tree = build(kb, mined, settings.db_path if args.with_logs else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.out, encoding="utf-8", xml_declaration=True)
    n = sum(1 for e in tree.getroot() if e.tag.endswith("NamedIndividual"))
    print(f"Đã ghi {args.out}: {len(CLASSES) + 8} lớp, {n} cá thể")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
