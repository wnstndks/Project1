"""The learn coach (DECISIONS.md D-034): evidence from my own records, what to check this
week, study material, and reading / self-check progress.

Not a signal, not a rule check, not a policy check and not advice; nothing here places an
order. `/skills` and `/week` load a year of bars and the rule checks, so they run off the
event loop; the lesson routes are static content plus a small progress table.
"""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.deps import get_learn_service
from app.schemas.learn import LessonOut, LessonsOut, ProgressIn, ProgressOut, SkillsOut, WeekOut
from app.services.learn import LearnService

router = APIRouter(prefix="/learn", tags=["learn"])


@router.get("/skills", response_model=SkillsOut)
async def get_skills(service: LearnService = Depends(get_learn_service)):
    return await run_in_threadpool(service.skills)


@router.get("/week", response_model=WeekOut)
async def get_week(service: LearnService = Depends(get_learn_service)):
    return await run_in_threadpool(service.week)


@router.get("/lessons", response_model=LessonsOut)
def list_lessons(service: LearnService = Depends(get_learn_service)):
    return service.lessons()


@router.get("/lessons/{lesson_id}", response_model=LessonOut)
def get_lesson(lesson_id: str, service: LearnService = Depends(get_learn_service)):
    return service.lesson(lesson_id)


@router.put("/progress/{lesson_id}", response_model=ProgressOut)
def put_progress(
    lesson_id: str, body: ProgressIn, service: LearnService = Depends(get_learn_service)
):
    return service.set_progress(lesson_id, body.read, body.answers)
