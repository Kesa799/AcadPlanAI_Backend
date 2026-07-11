import json
import re
from typing import Dict, Any, Optional, List
from app.config import settings

class AIService:
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.mock_mode = True  # Default to mock mode
        
        # Try to initialize OpenAI if key exists
        if self.api_key and not self._is_placeholder_key(self.api_key):
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
                self.mock_mode = False
                print("OpenAI client initialized successfully.")
            except Exception as e:
                print(f"OpenAI initialization failed: {str(e)}")
                print("Using mock mode instead.")
                self.mock_mode = True
        else:
            print("No OpenAI API key found. Using mock mode.")
            self.mock_mode = True
    
    def generate_cdp(self, syllabus_text: str, additional_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate CDP from syllabus text - extract what exists and fill defaults"""
        if self.mock_mode or not syllabus_text:
            extracted = self._extract_only_from_text(syllabus_text)
            return self._merge_with_defaults(extracted, syllabus_text)
        
        try:
            # Use OpenAI directly
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert educational curriculum designer. Extract ONLY the information that is explicitly present in the syllabus, but structure it to include all required fields with null/empty values where data is missing."},
                    {"role": "user", "content": self._create_extraction_prompt(syllabus_text, additional_prompt)}
                ],
                temperature=0.1,
                max_tokens=4000
            )
            
            # Extract JSON from response
            content = response.choices[0].message.content
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                json_str = re.sub(r'```json\s*', '', json_str)
                json_str = re.sub(r'```\s*', '', json_str)
                data = json.loads(json_str)
                return self._merge_with_defaults(data, syllabus_text)
            else:
                raise ValueError("No JSON found in response")
                
        except Exception as e:
            print(f"AI generation failed: {str(e)}")
            extracted = self._extract_only_from_text(syllabus_text)
            return self._merge_with_defaults(extracted, syllabus_text)

    def generate_local_cdp(self, syllabus_text: str) -> Dict[str, Any]:
        """Generate CDP from local parsing rules without calling an external API."""
        extracted = self._extract_only_from_text(syllabus_text)
        return self._merge_with_defaults(extracted, syllabus_text)
    
    def _create_extraction_prompt(self, syllabus_text: str, additional_prompt: Optional[str] = None) -> str:
        """Create the AI prompt for strict extraction"""
        return f"""
        You are an expert educational curriculum designer. Your task is to EXTRACT ONLY the information that is explicitly present in the syllabus text below.
        
        IMPORTANT RULES:
        1. ONLY include fields that are clearly stated in the syllabus
        2. DO NOT add any generated, inferred, or fallback content
        3. If a field is not present, DO NOT include it in the JSON
        4. Use NULL for values that are mentioned but have no content
        5. DO NOT generate course outcomes, weekly plans, or any other content that isn't explicitly in the syllabus
        
        SYLLABUS TEXT:
        {syllabus_text[:8000]}

        ADDITIONAL INSTRUCTIONS:
        {additional_prompt or "None"}
        
        Extract the following fields ONLY IF they exist in the syllabus:
        
        1. Basic Information (only if present):
           - course_name
           - course_code  
           - credits (in L-T-P-C format)
           - department
        
        2. Course Outcomes (only if explicitly listed):
           - Each CO with id and description (only if COs are mentioned)
        
        3. Program Outcomes (only if explicitly listed):
           - Each PO with id and description (only if POs are mentioned)
        
        4. Syllabus Content (only if present):
           - Units/Modules with their titles and topics
           - Week-wise breakdown if mentioned
        
        5. Evaluation Scheme (only if present):
           - Assessment components with weightage
        
        6. Textbooks/References (only if listed):
           - Author, title, publisher, year
        
        Return ONLY valid JSON with exactly the fields that exist in the syllabus. If a section doesn't exist, don't include it.
        """
    
    def _extract_only_from_text(self, syllabus_text: str) -> Dict[str, Any]:
        """Extract ONLY what exists in the syllabus text - no fallback content"""
        result = {}
        
        # Extract metadata only if present
        metadata = self._extract_metadata_only(syllabus_text)
        if metadata:
            result.update(metadata)
        
        # Extract course outcomes only if present
        course_outcomes = self._extract_course_outcomes_only(syllabus_text)
        if course_outcomes:
            result["course_outcomes"] = course_outcomes
        
        # Extract program outcomes only if present
        program_outcomes = self._extract_program_outcomes_only(syllabus_text)
        if program_outcomes:
            result["program_outcomes"] = program_outcomes
        
        # Extract units/topics only if present
        units = self._extract_units_only(syllabus_text)
        if units:
            result["syllabus_units"] = units
        
        # Extract evaluation scheme only if present
        evaluation = self._extract_evaluation_only(syllabus_text)
        if evaluation:
            result["evaluation_scheme"] = evaluation
        
        # Extract textbooks only if present
        textbooks = self._extract_textbooks_only(syllabus_text)
        if textbooks:
            result["textbooks"] = textbooks
        
        return result
    
    def _merge_with_defaults(self, extracted: Dict[str, Any], syllabus_text: str) -> Dict[str, Any]:
        """Merge extracted data with default values for all required fields"""
        
        # Start with extracted data
        result = extracted.copy()
        
        # 1. Basic Information - ensure all required fields exist
        if "course_name" not in result or not result["course_name"]:
            result["course_name"] = self._infer_course_name(syllabus_text) or "Course Delivery Plan"
        
        if "course_code" not in result or not result["course_code"]:
            result["course_code"] = self._extract_course_code(syllabus_text) or "COURSE101"
        
        if "credits" not in result or not result["credits"]:
            result["credits"] = self._extract_credits(syllabus_text) or "3-0-0-3"
        
        if "department" not in result or not result["department"]:
            result["department"] = self._extract_department_from_text(syllabus_text) or "Not specified"
        
        # 2. Academic Year (always required)
        if "academic_year" not in result or not result["academic_year"]:
            result["academic_year"] = "2024-25"  # Default current academic year
        
        # 3. Course Outcomes - ensure always present (even if empty list)
        if "course_outcomes" not in result:
            result["course_outcomes"] = []
        
        # 4. Program Outcomes - ensure always present (even if empty list)
        if "program_outcomes" not in result:
            result["program_outcomes"] = []
        
        # 5. Weekly Plan - ensure always present with empty list if not extracted
        if "weekly_plan" not in result or not result["weekly_plan"]:
            result["weekly_plan"] = []
        
        # 6. CO-PO Affinity Map - ensure always present with empty dict if not extracted
        if "co_po_affinity_map" not in result or not result["co_po_affinity_map"]:
            result["co_po_affinity_map"] = {}
        
        # 7. Concept Map - ensure always present with empty string if not extracted
        if "concept_map_mermaid" not in result or not result["concept_map_mermaid"]:
            result["concept_map_mermaid"] = ""
        
        # 8. Evaluation Scheme - ensure always present with default if not extracted
        if "evaluation_scheme" not in result or not result["evaluation_scheme"]:
            result["evaluation_scheme"] = [
                {"component": "Internal Assessment", "weightage": 30, "duration": None},
                {"component": "End Semester Examination", "weightage": 70, "duration": "3 hours"}
            ]
        
        return result
    
    def _extract_metadata_only(self, syllabus_text: str) -> Dict[str, str]:
        """Extract metadata ONLY if it exists in the text"""
        text = syllabus_text or ""
        result = {}
        
        # Look for course code and name pattern like "23ENG101 TECHNICAL COMMUNICATION"
        compact_course = re.search(
            r"^\s*([0-9]{2}[A-Z]{2,}\d{3}[A-Z]?)\s+(.+?)\s+L\s*-\s*T\s*-\s*P\s*-\s*C\s*:\s*(\d+\s*-\s*\d+\s*-\s*\d+\s*-\s*\d+)",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if compact_course:
            result["course_code"] = compact_course.group(1).strip()
            result["course_name"] = compact_course.group(2).strip()
            result["credits"] = compact_course.group(3).strip()
        else:
            # Try to find course code separately
            course_code = self._extract_field(text, [
                r"(?:course\s*code|code)\s*[:\-]\s*([A-Z0-9]{2,}[A-Z0-9\-/ ]{2,20})",
                r"\b([0-9]{2}[A-Z]{2,}\d{3}[A-Z]?)\b",
                r"\b([A-Z]{2,}\s*\d{2,4}[A-Z]?)\b",
            ])
            if course_code:
                result["course_code"] = course_code
            
            # Try to find course name separately
            course_name = self._extract_field(text, [
                r"(?:course\s*(?:title|name)|title)\s*[:\-]\s*([^\n\r]+)",
            ])
            if course_name:
                result["course_name"] = course_name
            
            # Try to find credits separately
            credits = self._extract_field(text, [
                r"(?:L\s*[-:]\s*T\s*[-:]\s*P\s*[-:]\s*C|L-T-P-C|credits?)\s*[:\-]?\s*(\d+\s*[-:]\s*\d+\s*[-:]\s*\d+\s*[-:]\s*\d+)",
                r"\b(\d+\s*-\s*\d+\s*-\s*\d+\s*-\s*\d+)\b",
            ])
            if credits:
                result["credits"] = re.sub(r"\s*[:\-]\s*", "-", credits).strip("-")
        
        # Extract department if present
        department = self._extract_field(text, [
            r"(?:department|dept\.?)\s*[:\-]\s*([^\n\r]+)",
            r"(?:programme|program)\s*[:\-]\s*([^\n\r]+)",
            r"(B\.?Tech\s*[- ]\s*[^\n\r]+)",
        ])
        if department:
            result["department"] = department
        
        return result
    
    def _extract_course_outcomes_only(self, syllabus_text: str) -> List[Dict[str, Any]]:
        """Extract course outcomes ONLY if they are explicitly listed"""
        text = syllabus_text or ""
        outcomes = []
        
        # Look for CO patterns
        co_matches = re.findall(r"\bCO\s*([1-9])\s*[:\-\.]?\s*([^\n\r]+)", text, re.IGNORECASE)
        for idx, (co_num, description) in enumerate(co_matches, 1):
            # Clean the description - stop at next CO or common separators
            description = re.split(r"\s{2,}| CO\d+\b|;", description)[0]
            description = self._clean_text(description)
            if description and len(description) > 5:  # Only include if it's a real description
                outcomes.append({
                    "id": f"CO{idx}",
                    "description": description
                })
        
        # Also look for "Course Outcomes" section
        if not outcomes:
            co_section = re.search(
                r"Course\s+Outcomes?\s*(.*?)(?=\n\s*(?:Syllabus|Unit|Module|References|Evaluation|$))",
                text,
                re.IGNORECASE | re.DOTALL
            )
            if co_section:
                lines = co_section.group(1).splitlines()
                for line in lines:
                    line = self._clean_text(line)
                    if re.match(r"^CO\d+", line, re.IGNORECASE):
                        match = re.search(r"CO\d+\s*[:\-\.]?\s*(.+)", line, re.IGNORECASE)
                        if match:
                            outcomes.append({
                                "id": match.group(0).split()[0] if match.group(0) else f"CO{len(outcomes)+1}",
                                "description": self._clean_text(match.group(1))
                            })
        
        return outcomes
    
    def _extract_program_outcomes_only(self, syllabus_text: str) -> List[Dict[str, str]]:
        """Extract program outcomes ONLY if they are explicitly listed"""
        text = syllabus_text or ""
        outcomes = []
        
        # Look for PO patterns
        po_matches = re.findall(r"\bPO\s*([1-9][0-9]?)\s*[:\-\.]?\s*([^\n\r]+)", text, re.IGNORECASE)
        for po_num, description in po_matches:
            description = self._clean_text(description)
            if description and len(description) > 5:
                outcomes.append({
                    "id": f"PO{po_num}",
                    "description": description
                })
        
        return outcomes
    
    def _extract_units_only(self, syllabus_text: str) -> List[Dict[str, Any]]:
        """Extract units/modules ONLY if they are explicitly listed"""
        text = syllabus_text or ""
        units = []
        
        # Find unit/module sections
        unit_section = re.search(
            r"(?:Syllabus|Unit|Module)\s*(.*?)(?=\n\s*(?:References|Evaluation Pattern|Assessment|Course Outcomes|$))",
            text,
            re.IGNORECASE | re.DOTALL
        )
        
        if unit_section:
            unit_text = unit_section.group(0)
            
            # Split by unit/module markers
            unit_blocks = re.split(
                r"\n\s*(?:Unit|Module)\s*[-:]?\s*(?:[IVX]+|\d+)?\s*[:\-]?\s*",
                unit_text,
                re.IGNORECASE
            )
            
            for block in unit_blocks[1:]:  # Skip the first part before any unit
                lines = block.splitlines()
                if lines:
                    # First line is the unit title
                    title = self._clean_text(lines[0])
                    if title:
                        # Rest are topics/content
                        topics = []
                        for line in lines[1:]:
                            cleaned = self._clean_text(line)
                            if cleaned and not cleaned.startswith("Unit") and not cleaned.startswith("Module"):
                                topics.append(cleaned)
                        
                        units.append({
                            "title": title,
                            "topics": topics if topics else []
                        })
        
        return units
    
    def _extract_evaluation_only(self, syllabus_text: str) -> List[Dict[str, Any]]:
        """Extract evaluation scheme ONLY if it's explicitly mentioned"""
        text = syllabus_text or ""
        evaluation = []
        
        # Look for evaluation pattern
        eval_section = re.search(
            r"(?:Evaluation Pattern|Assessment|Evaluation)\s*(.*?)(?=\n\s*(?:References|Textbooks|Syllabus|Course Outcomes|$))",
            text,
            re.IGNORECASE | re.DOTALL
        )
        
        if eval_section:
            eval_text = eval_section.group(0)
            
            # Try to find table-like structure
            table_match = re.search(
                r"<table>(.*?)</table>",
                eval_text,
                re.IGNORECASE | re.DOTALL
            )
            
            if table_match:
                # Parse HTML table
                rows = re.findall(r"<tr>(.*?)</tr>", table_match.group(1), re.DOTALL)
                for row in rows[1:]:  # Skip header row
                    cells = re.findall(r"<td>(.*?)</td>", row, re.DOTALL)
                    if len(cells) >= 2:
                        component = self._clean_text(cells[0])
                        weightage = self._clean_text(cells[1])
                        if component and weightage:
                            try:
                                weightage_val = int(re.sub(r"[^0-9]", "", weightage))
                                evaluation.append({
                                    "component": component,
                                    "weightage": weightage_val
                                })
                            except:
                                evaluation.append({
                                    "component": component,
                                    "weightage": weightage
                                })
            else:
                # Try to parse text format
                lines = eval_text.splitlines()
                for line in lines:
                    line = self._clean_text(line)
                    if ":" in line:
                        parts = line.split(":")
                        if len(parts) >= 2:
                            component = self._clean_text(parts[0])
                            weightage = self._clean_text(parts[1])
                            if component and weightage:
                                try:
                                    weightage_val = int(re.sub(r"[^0-9]", "", weightage))
                                    evaluation.append({
                                        "component": component,
                                        "weightage": weightage_val
                                    })
                                except:
                                    evaluation.append({
                                        "component": component,
                                        "weightage": weightage
                                    })
        
        return evaluation
    
    def _extract_textbooks_only(self, syllabus_text: str) -> List[Dict[str, Any]]:
        """Extract textbooks/references ONLY if they are listed"""
        text = syllabus_text or ""
        textbooks = []
        
        # Look for references section
        refs_match = re.search(
            r"References?\(s\)?\s*(.*?)(?=\n\s*(?:Evaluation Pattern|Assessment|Course Outcomes|Syllabus|$))",
            text,
            re.IGNORECASE | re.DOTALL
        )
        
        if refs_match:
            refs_text = refs_match.group(1)
            
            # Split by common separators
            refs = re.split(r"[,;.]", refs_text)
            
            for ref in refs:
                ref = self._clean_text(ref)
                if ref and len(ref) > 10:  # Only include meaningful references
                    book = {}
                    
                    # Try to extract author
                    author_match = re.search(r"^([A-Z][a-z]+\.?\s+[A-Z][a-z]+)", ref)
                    if author_match:
                        book["author"] = author_match.group(1)
                        title_part = ref[len(author_match.group(1)):].strip()
                    else:
                        # Try to find author pattern
                        author_match = re.search(r"([A-Z][a-z]+\.?\s+[A-Z][a-z]+\s+[A-Z][a-z]+)", ref)
                        if author_match:
                            book["author"] = author_match.group(1)
                            title_part = ref.replace(author_match.group(1), "").strip()
                        else:
                            title_part = ref
                    
                    # Try to extract year
                    year_match = re.search(r"\b(19|20)\d{2}\b", title_part)
                    if year_match:
                        book["year"] = int(year_match.group(0))
                        title_part = title_part.replace(year_match.group(0), "").strip()
                    
                    # Clean the title
                    title_part = re.sub(r"^[,\s.]+|[,\s.]+$", "", title_part)
                    title_part = re.sub(r"\s+", " ", title_part)
                    
                    if title_part and len(title_part) > 5:
                        book["title"] = title_part
                        if "author" not in book:
                            book["author"] = "Not specified"
                        textbooks.append(book)
        
        return textbooks
    
    def _extract_field(self, text: str, patterns: List[str]) -> Optional[str]:
        """Extract a field using multiple patterns"""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self._clean_text(match.group(1))
        return None
    
    def _clean_text(self, value: str) -> str:
        """Clean text by removing extra whitespace"""
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value).strip(" :-\t\n\r"))
    
    def _infer_course_name(self, text: str) -> str:
        """Infer course name from text if not explicitly found"""
        for line in text.splitlines()[:30]:
            cleaned = self._clean_text(line)
            if 4 <= len(cleaned) <= 90 and not re.search(r"university|department|semester|credits?", cleaned, re.IGNORECASE):
                return cleaned
        return "Course Delivery Plan"
    
    def _extract_course_code(self, text: str) -> Optional[str]:
        """Extract course code from text"""
        patterns = [
            r"^\s*([0-9]{2}[A-Z]{2,}\d{3}[A-Z]?)",
            r"(?:course\s*code|code)\s*[:\-]\s*([A-Z0-9]{2,}[A-Z0-9\-/ ]{2,20})",
            r"\b([0-9]{2}[A-Z]{2,}\d{3}[A-Z]?)\b",
            r"\b([A-Z]{2,}\s*\d{2,4}[A-Z]?)\b",
        ]
        return self._extract_field(text, patterns)
    
    def _extract_credits(self, text: str) -> Optional[str]:
        """Extract credits from text"""
        patterns = [
            r"(?:L\s*[-:]\s*T\s*[-:]\s*P\s*[-:]\s*C|L-T-P-C|credits?)\s*[:\-]?\s*(\d+\s*[-:]\s*\d+\s*[-:]\s*\d+\s*[-:]\s*\d+)",
            r"\b(\d+\s*-\s*\d+\s*-\s*\d+\s*-\s*\d+)\b",
        ]
        credits = self._extract_field(text, patterns)
        if credits:
            return re.sub(r"\s*[:\-]\s*", "-", credits).strip("-")
        return None
    
    def _extract_department_from_text(self, syllabus_text: str) -> Optional[str]:
        """Extract department if present"""
        dept_match = re.search(r"(?:department|dept\.?)\s*[:\-]\s*([^\n\r]+)", syllabus_text, re.IGNORECASE)
        if dept_match:
            return self._clean_text(dept_match.group(1))
        
        program_match = re.search(r"(?:programme|program)\s*[:\-]\s*([^\n\r]+)", syllabus_text, re.IGNORECASE)
        if program_match:
            return self._clean_text(program_match.group(1))
        
        return None
    
    def _extract_topic_titles(self, syllabus_text: str) -> List[str]:
        """Extract topic titles from syllabus text"""
        text = syllabus_text or ""
        topics = []
        
        # Look for unit/module blocks
        unit_blocks = re.findall(
            r"(?:Unit|Module)\s*[-:]?\s*(?:[IVX]+|\d+)?\s*[:\-]?\s*(.*?)(?=(?:\n\s*(?:Unit|Module)\s*[-:]?\s*(?:[IVX]+|\d+))|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        
        for block in unit_blocks:
            first_line = next((line.strip() for line in block.splitlines() if line.strip()), "")
            if first_line:
                topics.append(first_line)
            for piece in re.split(r"[,;\u2022]", block):
                cleaned = self._clean_text(piece)
                if 3 <= len(cleaned.split()) <= 12:
                    topics.append(cleaned)
        
        if not topics:
            for line in text.splitlines():
                cleaned = self._clean_text(line)
                if re.match(r"^(?:\d+\.|[A-Z]\)|Unit|Module|Chapter)\s+", cleaned, re.IGNORECASE):
                    topics.append(re.sub(r"^(?:\d+\.|[A-Z]\))\s*", "", cleaned))
        
        return self._dedupe([topic for topic in topics if topic and len(topic) <= 120])
    
    def _dedupe(self, values: List[str]) -> List[str]:
        """Remove duplicate entries while preserving order"""
        seen = set()
        result = []
        for value in values:
            key = value.lower()
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result
    
    def _is_placeholder_key(self, api_key: str) -> bool:
        """Check if the API key is a placeholder"""
        normalized = api_key.strip().lower()
        return (
            normalized in {"", "none", "null", "your_openai_api_key_here"}
            or "your_" in normalized
            or "placeholder" in normalized
        )