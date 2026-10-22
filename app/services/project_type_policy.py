from app.domain.models import ProjectType


SCIENCE_VISUAL_CONSTRAINT = (
    "科普画面禁止出现人类、主持人、旁观者、手部演示、人物剪影及拟人化角色；"
    "原文明确的真实动物、昆虫等生物主体可以出现并保持非拟人化；"
    "只展示真实对象、自然过程、实验装置或非拟人化的科学示意。"
)


def is_science(project_type: ProjectType | str | None) -> bool:
    return project_type == "science"


def visual_constraint(project_type: ProjectType | str | None) -> str:
    return SCIENCE_VISUAL_CONSTRAINT if is_science(project_type) else ""
