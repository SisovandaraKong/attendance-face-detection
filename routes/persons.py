"""
routes/persons.py
─────────────────────────────────────────────────────────────
Person management page + JSON API.

Shows who is enrolled in the system, how many images each
person has, and whether their dataset is complete.
─────────────────────────────────────────────────────────────
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from schemas.attendance import APIResponse, PersonInfo, PersonListResponse

router    = APIRouter(prefix="/persons", tags=["persons"])
templates = Jinja2Templates(directory="templates")

# Paths from project root
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR  = os.path.join(BASE_DIR, "dataset")

# 7 zones × 30 images × 5 augmentations = 1050 images per person
IMAGES_PER_ZONE    = 30
NUM_ZONES          = 7
AUGMENT_FACTOR     = 5
TOTAL_IMAGES_NEEDED = IMAGES_PER_ZONE * NUM_ZONES * AUGMENT_FACTOR


def _list_persons() -> list[PersonInfo]:
    """Scan the dataset directory and build PersonInfo for each subdirectory."""
    if not os.path.isdir(DATASET_DIR):
        return []

    persons = []
    for name in sorted(os.listdir(DATASET_DIR)):
        person_path = os.path.join(DATASET_DIR, name)
        if not os.path.isdir(person_path):
            continue

        count = len([
            f for f in os.listdir(person_path)
            if f.lower().endswith((".jpg", ".png", ".jpeg"))
        ])
        persons.append(PersonInfo(
            name=name,
            display_name=name.replace("_", " "),
            image_count=count,
            complete=(count >= TOTAL_IMAGES_NEEDED),
        ))
    return persons


@router.get("/", response_class=HTMLResponse)
async def persons_page(request: Request) -> HTMLResponse:
    """Person management page."""
    persons = _list_persons()
    return templates.TemplateResponse(request, "persons.html", {
        "persons":       persons,
        "total_needed":  TOTAL_IMAGES_NEEDED,
        "known_persons": request.app.state.face_service.known_persons,
    })


# ── JSON API ─────────────────────────────────────────────────

@router.get("/api/list", response_model=PersonListResponse)
async def api_list_persons() -> PersonListResponse:
    """Return all enrolled persons with dataset completion status."""
    try:
        persons = _list_persons()
        return PersonListResponse(
            success=True,
            data=persons,
            message=f"{len(persons)} person(s) enrolled",
        )
    except Exception as exc:
        return PersonListResponse(
            success=False,
            data=[],
            message=str(exc),
        )


@router.get("/api/stats", response_model=APIResponse)
async def api_person_stats() -> APIResponse:
    """Return aggregate dataset stats."""
    persons = _list_persons()
    total_images = sum(p.image_count for p in persons)
    complete     = sum(1 for p in persons if p.complete)
    return APIResponse(
        success=True,
        data={
            "total_persons": len(persons),
            "complete":      complete,
            "incomplete":    len(persons) - complete,
            "total_images":  total_images,
        },
        message="Dataset statistics",
    )
