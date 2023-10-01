from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class ObjectivesOutcomes(BaseModel):
    learning_objectives: List[str] = Field(..., json_schema_extra={"description": "List of learning objectives for the course"})
    skills_development: List[str] = Field(..., json_schema_extra={"description": "List of skills to be developed during the course"})

class LessonPlan(BaseModel):
    topic: str = Field(..., json_schema_extra={"description": "The topic for the lesson"})
    objectives: List[str] = Field(..., json_schema_extra={"description": "Learning objectives for the lesson"})
    activities: List[str] = Field(..., json_schema_extra={"description": "Activities planned for the lesson"})
    materials_needed: List[str] = Field(..., json_schema_extra={"description": "Materials needed for the lesson"})

class UnitModule(BaseModel):
    title: str = Field(..., json_schema_extra={"description": "Title of the unit or module"})
    duration_weeks: int = Field(..., json_schema_extra={"description": "Duration of the unit in weeks"})
    lesson_plans: List[LessonPlan] = Field(..., json_schema_extra={"description": "List of lesson plans in the unit"})

class TimeConstrainedModel(BaseModel):
    start_week_number: Optional[int] = Field(None, json_schema_extra={"description": "Start time for the activity"})
    end_week_number: Optional[int] = Field(None, json_schema_extra={"description": "End time for the activity"})
    time_limit_minutes: Optional[int] = Field(None, json_schema_extra={"description": "Time limit in minutes"})

class FormativeAssessment(TimeConstrainedModel):
    type: str = Field(..., json_schema_extra={"description": "Type of formative assessment"})
    description: str = Field(..., json_schema_extra={"description": "Description of the formative assessment"})
    weightage: float = Field(..., json_schema_extra={"description": "Weightage of the assessment in the overall grade"})

# Update SummativeAssessment model
class SummativeAssessment(TimeConstrainedModel):
    type: str = Field(..., json_schema_extra={"description": "Type of summative assessment"})
    description: str = Field(..., json_schema_extra={"description": "Description of the summative assessment"})
    weightage: float = Field(..., json_schema_extra={"description": "Weightage of the assessment in the overall grade"})

class HomeworkAssignment(TimeConstrainedModel):
    description: str = Field(..., json_schema_extra={"description": "Description of the homework"})

class ProjectAssignment(TimeConstrainedModel):
    description: str = Field(..., json_schema_extra={"description": "Description of the project"})

class AdditionalComponents(BaseModel):
    homework_assignments: List[HomeworkAssignment] = Field(..., json_schema_extra={"description": "List of homework assignments"})
    projects: List[ProjectAssignment] = Field(..., json_schema_extra={"description": "List of projects"})
    extra_reading_resources: List[str] = Field(..., json_schema_extra={"description": "List of additional reading materials"})

class GradeBoundary(BaseModel):
    grade: str = Field(..., json_schema_extra={"description": "The grade, e.g., A, B, C etc."})
    lower_bound: float = Field(..., json_schema_extra={"description": "The lower bound for this grade"})
    upper_bound: float = Field(..., json_schema_extra={"description": "The upper bound for this grade"})
    
class GradingScheme(BaseModel):
    total_score: int = Field(..., json_schema_extra={"description": "Total possible score in the course"})
    grade_boundaries: List[GradeBoundary] = Field(..., json_schema_extra={"description": "Boundaries for each grade level"})

class AdditionalComponents(BaseModel):
    homework_assignments: List[str] = Field(..., json_schema_extra={"description": "List of homework assignments"})
    projects: List[str] = Field(..., json_schema_extra={"description": "List of projects"})
    extra_reading_resources: List[str] = Field(..., json_schema_extra={"description": "List of additional reading materials"})

class SupplementalMaterial(BaseModel):
    textbooks: List[str] = Field(..., json_schema_extra={"description": "List of textbooks used for the course"})
    references: List[str] = Field(..., json_schema_extra={"description": "Additional references for the course"})
    tech_requirements: List[str] = Field(..., json_schema_extra={"description": "Technical requirements for the course"})

class CourseCurriculum(BaseModel):
    course_title: str = Field(..., json_schema_extra={"description": "Title of the course"})
    course_description: str = Field(..., json_schema_extra={"description": "Brief description of the course"})
    target_audience: str = Field(..., json_schema_extra={"description": "Target audience for the course"})
    course_weeks: int = Field(..., json_schema_extra={"description": "Duration of the course in weeks"})
    objectives_outcomes: ObjectivesOutcomes = Field(..., json_schema_extra={"description": "Learning objectives and skills development"})
    units_modules: List[UnitModule] = Field(..., json_schema_extra={"description": "Units or modules to be covered in the course"})
    formative_assessments: List[FormativeAssessment] = Field(..., json_schema_extra={"description": "List of formative assessments"})
    summative_assessments: List[SummativeAssessment] = Field(..., json_schema_extra={"description": "List of summative assessments"})
    additional_components: AdditionalComponents = Field(..., json_schema_extra={"description": "Additional components like homework and projects"})
    grading_scheme: GradingScheme = Field(..., json_schema_extra={"description": "Grading scheme and grade boundaries"})
    supplemental_material: SupplementalMaterial = Field(..., json_schema_extra={"description": "Supplemental materials like textbooks and tech requirements"})

class StudentCurriculumInput(BaseModel):
    course_name: str = Field(..., json_schema_extra={"description": "Name of the course"})
    book_name: Optional[str] = Field(None, json_schema_extra={"description": "Name of the book to be used"})
    academic_goals: Optional[List[str]] = Field(None, json_schema_extra={"description": "Academic goals for the course"})
    interested_topics: Optional[List[str]] = Field(None, json_schema_extra={"description": "Specific topics the student is interested in"})
    assessment_types: Optional[List[str]] = Field(None, json_schema_extra={"description": "Preferred types of assessments"})
    course_pace: Optional[str] = Field(None, json_schema_extra={"description": "Desired pace of the course"})

    def format_for_ai(self) -> str:
        return f"Course Name: {self.course_name}\nBook Name: {self.book_name or 'Not specified'}\nAcademic Goals: {', '.join(self.academic_goals) if self.academic_goals else 'Not specified'}\nInterested Topics: {', '.join(self.interested_topics) if self.interested_topics else 'Not specified'}\nAssessment Types: {', '.join(self.assessment_types) if self.assessment_types else 'Not specified'}\nCourse Pace: {self.course_pace or 'Not specified'}"