from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import GLCode
from backend.schemas import GLCodeOut, GLCodeHierarchy

router = APIRouter(tags=["gl_codes"])


def _build_hierarchy(codes: list[GLCode]) -> list[GLCodeHierarchy]:
    """Build a nested hierarchy from a flat list of GL codes.

    Assumes gl_code numbering encodes hierarchy:
    - Level 1: e.g. 5000
    - Level 2: e.g. 5100 (child of 5000)
    - Level 3: e.g. 5110 (child of 5100)

    Parent is determined by finding the nearest code at a lower level
    whose gl_code value is less than the current code.
    """
    nodes: dict[int, GLCodeHierarchy] = {}
    roots: list[GLCodeHierarchy] = []

    # Sort by gl_code to ensure parents come before children
    sorted_codes = sorted(codes, key=lambda c: c.gl_code)

    # Track the last seen node at each level for parent assignment
    level_stack: dict[int, GLCodeHierarchy] = {}

    for code in sorted_codes:
        node = GLCodeHierarchy(
            gl_code=code.gl_code,
            gl_class=code.gl_class,
            gl_level=code.gl_level,
            description=code.description,
        )
        nodes[code.gl_code] = node

        if code.gl_level == 1:
            roots.append(node)
        else:
            # Find parent: the last node at a level one above
            parent = level_stack.get(code.gl_level - 1)
            if parent:
                parent.children.append(node)
            else:
                roots.append(node)

        level_stack[code.gl_level] = node

    return roots


@router.get("/gl-codes", response_model=list[GLCodeOut] | list[GLCodeHierarchy])
def list_gl_codes(
    level: Optional[int] = Query(None, description="Filter to a specific level for a flat list"),
    db: Session = Depends(get_db),
):
    if level is not None:
        codes = (
            db.query(GLCode)
            .filter(GLCode.gl_level == level)
            .order_by(GLCode.gl_code)
            .all()
        )
        return [GLCodeOut.model_validate(c) for c in codes]

    # Return full hierarchy
    codes = db.query(GLCode).order_by(GLCode.gl_code).all()
    return _build_hierarchy(codes)
