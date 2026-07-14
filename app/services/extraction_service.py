import re
from typing import Dict, Any, Optional, List


class ExtractionService:
    """
    Builds a Course Delivery Plan (CDP) purely by extracting text/values that are
    literally present in the uploaded syllabus. No AI/LLM calls are made and no
    field is invented, padded, or filled with generic/template content.

    Any section that cannot be confidently found in the syllabus text is left
    empty (list/dict) or null (scalar) rather than guessed.
    """

    def extract_cdp(self, syllabus_text: str) -> Dict[str, Any]:
        text = syllabus_text or ""

        metadata = self._extract_metadata(text)
        academic_year = self._extract_academic_year(text)
        units = self._extract_units(text)
        course_outcomes, program_outcomes = self._extract_outcomes(text)
        weekly_plan = self._build_weekly_plan(units)
        evaluation_scheme = self._extract_evaluation_scheme(text)
        affinity_map = self._extract_affinity_map(text, program_outcomes)
        textbooks = self._extract_textbooks(text)
        prerequisites = self._extract_prerequisites(text)
        concept_map = self._build_concept_map(metadata, units)

        return {
            "course_name": metadata["course_name"],
            "course_code": metadata["course_code"],
            "credits": metadata["credits"],
            "department": metadata["department"],
            "academic_year": academic_year,
            "course_outcomes": course_outcomes,
            "program_outcomes": program_outcomes,
            "weekly_plan": weekly_plan,
            "evaluation_scheme": evaluation_scheme,
            "co_po_affinity_map": affinity_map,
            "concept_map_mermaid": concept_map,
            "textbooks": textbooks,
            "prerequisites": prerequisites,
        }

    # ------------------------------------------------------------------
    # Basic metadata
    # ------------------------------------------------------------------
    def _extract_metadata(self, text: str) -> Dict[str, Optional[str]]:
        compact_course = re.search(
            r"^\s*([0-9]{2}[A-Z]{2,}\d{3}[A-Z]?)\s+(.+?)\s+L\s*-\s*T\s*-\s*P\s*-\s*C\s*:\s*(\d+\s*-\s*\d+\s*-\s*\d+\s*-\s*\d+)",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if compact_course:
            course_code = compact_course.group(1)
            course_name = compact_course.group(2)
            credits = compact_course.group(3)
        else:
            course_code = self._first_match(text, [
                r"(?:course\s*code|code)\s*[:\-]\s*([A-Z0-9]{2,}[A-Z0-9\-/ ]{2,20})",
                r"\b([0-9]{2}[A-Z]{2,}\d{3}[A-Z]?)\b",
                r"\b([A-Z]{2,}\s*\d{2,4}[A-Z]?)\b",
            ], None)
            course_name = self._first_match(text, [
                r"(?:course\s*(?:title|name)|title)\s*[:\-]\s*([^\n\r]+)",
                r"(?:name\s*of\s*(?:the\s*)?course)\s*[:\-]\s*([^\n\r]+)",
            ], None)
            if not course_name:
                course_name = self._infer_course_name(text)

            credits = self._first_match(text, [
                r"(?:L\s*[-:]\s*T\s*[-:]\s*P\s*[-:]\s*C|L-T-P-C|credits?)\s*[:\-]?\s*(\d+\s*[-:]\s*\d+\s*[-:]\s*\d+\s*[-:]\s*\d+)",
                r"\b(\d+\s*-\s*\d+\s*-\s*\d+\s*-\s*\d+)\b",
            ], None)

        if credits:
            credits = re.sub(r"\s*[:\-]\s*", "-", credits).strip("-")
            if not re.match(r"^\d+-\d+-\d+-\d+$", credits):
                credits = None

        department = self._first_match(text, [
            r"(?:department|dept\.?)\s*[:\-]\s*([^\n\r]+)",
            r"(?:programme|program)\s*[:\-]\s*([^\n\r]+)",
            r"(B\.?Tech\s*[- ]\s*[^\n\r]+)",
        ], None)

        return {
            "course_name": self._clean_or_none(course_name),
            "course_code": self._clean_or_none(course_code, strip_spaces=True),
            "credits": credits,
            "department": self._clean_or_none(department),
        }

    def _extract_academic_year(self, text: str) -> Optional[str]:
        value = self._first_match(text, [
            r"academic\s*year\s*[:\-]\s*(\d{4}\s*[-\/]\s*\d{2,4})",
        ], None)
        if value:
            value = re.sub(r"\s*[-/]\s*", "-", value).strip("-")
        return value

    def _infer_course_name(self, text: str) -> Optional[str]:
        for line in text.splitlines()[:30]:
            cleaned = self._clean_text(line)
            if 4 <= len(cleaned) <= 90 and not re.search(
                r"university|department|semester|credits?", cleaned, re.IGNORECASE
            ):
                return cleaned
        return None

    # ------------------------------------------------------------------
    # Units / Weekly plan (built only from Unit/Module blocks actually in the text)
    # ------------------------------------------------------------------
    def _extract_units(self, text: str) -> List[Dict[str, Any]]:
        units: List[Dict[str, Any]] = []
        unit_blocks = re.findall(
            r"(?:Unit|Module)\s*[-:]?\s*(?:[IVXLC]+|\d+)?\s*[:\-]?\s*(.*?)"
            r"(?=(?:\n\s*(?:Unit|Module)\s*[-:]?\s*(?:[IVXLC]+|\d+))|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )

        for block in unit_blocks:
            first_line = next((line.strip() for line in block.splitlines() if line.strip()), "")
            if not first_line or len(first_line) > 150:
                continue
            hours_match = re.search(r"(\d{1,3})\s*(?:hours?|hrs?)\b", block, re.IGNORECASE)
            # Strip a trailing "(9 hours)" style mention from the title itself,
            # since the hour count is already captured separately.
            title = re.sub(r"[\(\[]?\s*\d{1,3}\s*(?:hours?|hrs?)\s*[\)\]]?\s*$", "", first_line, flags=re.IGNORECASE)
            units.append({
                "title": self._clean_text(title),
                "hours": hours_match.group(1) if hours_match else None,
            })

        # De-duplicate while preserving order
        seen = set()
        deduped = []
        for unit in units:
            key = unit["title"].lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(unit)
        return deduped[:26]

    def _build_weekly_plan(self, units: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        weekly_plan = []
        for index, unit in enumerate(units, start=1):
            weekly_plan.append({
                "week": index,
                "topics": [{
                    "id": f"T{index}",
                    "title": unit["title"],
                    "duration": None,
                    "description": None,
                    "prerequisites": [],
                    "learning_objectives": [],
                    "assessment_methods": [],
                }],
                "total_hours": unit["hours"],
            })
        return weekly_plan

    # ------------------------------------------------------------------
    # Course Outcomes / Program Outcomes (only what is literally written)
    # ------------------------------------------------------------------
    def _extract_outcomes(self, text: str):
        # Anchored at line start so inline mentions like "(PO1, PO2)" inside a
        # CO description are not mistaken for a CO/PO definition line.
        co_matches = re.findall(r"^\s*CO\s*([1-9][0-9]?)\s*[:\-\.]?\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        course_outcomes = []
        for co_num, description in co_matches[:15]:
            description = re.split(r"\s{2,}|\s(?=CO\d+\b)", description)[0].strip()
            # Skip rows that are really a CO-PO correlation matrix row (e.g. "CO1 3 2 -")
            if re.fullmatch(r"[\d\-\s]+", description):
                continue
            mapped_pos = sorted(set(re.findall(r"\bPO\s*(\d{1,2})\b", description, re.IGNORECASE)),
                                 key=lambda n: int(n))
            course_outcomes.append({
                "id": f"CO{co_num}",
                "description": self._clean_text(description),
                "mapped_pos": [f"PO{n}" for n in mapped_pos],
            })

        po_matches = re.findall(r"^\s*PO\s*([1-9][0-9]?)\s*[:\-\.]?\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        program_outcomes = []
        for po_num, description in po_matches[:15]:
            description = re.split(r"\s{2,}|\s(?=PO\d+\b)", description)[0].strip()
            if not description or re.fullmatch(r"[\d\-\s,]+", description):
                continue
            program_outcomes.append({
                "id": f"PO{po_num}",
                "description": self._clean_text(description),
            })

        return course_outcomes, program_outcomes

    # ------------------------------------------------------------------
    # Evaluation scheme (only rows with an explicit weightage % in the text)
    # ------------------------------------------------------------------
    def _extract_evaluation_scheme(self, text: str) -> List[Dict[str, Any]]:
        section_match = re.search(
            r"(?:Evaluation\s*(?:Pattern|Scheme)|Assessment\s*Pattern)\s*[:\-]?\s*"
            r"(.*?)(?=\n\s*(?:References?|Text\s*Books?|Course\s*Outcomes?|Syllabus)\b|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        search_text = section_match.group(1) if section_match else text

        rows = []
        for match in re.finditer(r"([A-Za-z][A-Za-z /\-]{2,40}?)\s*[:\-]?\s*(\d{1,3})\s*%", search_text):
            component = self._clean_text(match.group(1))
            weightage = int(match.group(2))
            if not component or not (0 <= weightage <= 100):
                continue
            rows.append({"component": component, "weightage": weightage, "duration": None})
        return rows

    # ------------------------------------------------------------------
    # CO-PO affinity map (only from an explicit correlation matrix in the text)
    # ------------------------------------------------------------------
    def _extract_affinity_map(self, text: str, program_outcomes: List[Dict[str, str]]) -> Dict[str, Dict[str, float]]:
        po_ids = [po["id"] for po in program_outcomes]
        affinity: Dict[str, Dict[str, float]] = {}

        for line in text.splitlines():
            row_match = re.match(r"^\s*CO\s*([1-9][0-9]?)\s+([0-9\-\s]+)$", line, re.IGNORECASE)
            if not row_match:
                continue
            co_id = f"CO{row_match.group(1)}"
            values = row_match.group(2).split()
            if not values:
                continue
            scores = {}
            for idx, value in enumerate(values):
                if value == "-" or not value.isdigit():
                    continue
                po_id = po_ids[idx] if idx < len(po_ids) else f"PO{idx + 1}"
                scores[po_id] = float(value)
            if scores:
                affinity[co_id] = scores

        return affinity

    # ------------------------------------------------------------------
    # Concept map — a structural view built only from units actually found
    # ------------------------------------------------------------------
    def _build_concept_map(self, metadata: Dict[str, Optional[str]], units: List[Dict[str, Any]]) -> Optional[str]:
        if not units:
            return None
        root_label = metadata.get("course_code") or metadata.get("course_name")
        if not root_label:
            return None
        safe_course = self._mermaid_label(root_label)
        lines = ["graph TD", f"    A[{safe_course}]"]
        for index, unit in enumerate(units[:8], 1):
            label = self._mermaid_label(unit["title"])
            lines.append(f"    A --> T{index}[{label}]")
            if index > 1:
                lines.append(f"    T{index - 1} --> T{index}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Textbooks / prerequisites
    # ------------------------------------------------------------------
    def _extract_textbooks(self, text: str) -> List[Dict[str, Any]]:
        refs_match = re.search(
            r"References?\(s\)?\s*(.*?)(?=\n\s*(?:Evaluation Pattern|Assessment|Course Outcomes|Syllabus)\b|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not refs_match:
            return []

        books = []
        for raw_line in refs_match.group(1).splitlines():
            line = self._clean_text(raw_line)
            if not line or len(line) < 12:
                continue
            year_match = re.search(r"\b(19|20)\d{2}\b", line)
            year = int(year_match.group(0)) if year_match else None
            author = None
            title = line
            if "." in line:
                first, rest = line.split(".", 1)
                if len(first.split()) <= 8:
                    author = first.strip()
                    title = rest.strip()
            books.append({
                "title": title[:180],
                "author": author[:100] if author else None,
                "publisher": None,
                "year": year,
            })
            if len(books) == 6:
                break
        return books

    def _extract_prerequisites(self, text: str) -> List[str]:
        prereq = self._first_match(text, [
            r"(?:pre[-\s]?requisites?|prerequisites?)\s*[:\-]\s*([^\n\r]+)"
        ], None)
        if not prereq:
            return []
        return [self._clean_text(item) for item in re.split(r"[,;]", prereq) if self._clean_text(item)]

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _first_match(self, text: str, patterns: List[str], default: Optional[str]) -> Optional[str]:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return default

    def _clean_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip(" :-\t")

    def _clean_or_none(self, value: Optional[str], strip_spaces: bool = False) -> Optional[str]:
        if not value:
            return None
        cleaned = self._clean_text(value)
        if strip_spaces:
            cleaned = cleaned.replace(" ", "")
        return cleaned or None

    def _mermaid_label(self, value: str) -> str:
        return re.sub(r"[\[\]{}|]", "", self._clean_text(value))[:60]
