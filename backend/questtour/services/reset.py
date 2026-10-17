import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from questtour.models import AnswerAttempt, Assignment, GameRun, Photo, RunDevice, TeamAlbum
from questtour.storage import BlobStore

log = logging.getLogger("questtour.reset")


def reset_run(session: Session, assignment: Assignment, run: GameRun) -> tuple[list[str], list[str]]:
    """R-25: delete a service run and everything recorded for it; returns the photo and album blob
    names to remove once the transaction has committed. Children are deleted explicitly: SQLite
    does not enforce the ON DELETE CASCADE foreign keys, and attempts/photos/devices have no ORM
    cascade. The memories album (issue #33) belongs to the assignment, so it must go too –
    otherwise a live album would keep serving the previous run's PDF after the reset."""
    task_ids = [task.id for task in run.tasks]
    blob_names = list(
        session.scalars(select(Photo.blob_name).where(Photo.run_task_id.in_(task_ids)))
    )
    session.execute(delete(Photo).where(Photo.run_task_id.in_(task_ids)))
    session.execute(delete(AnswerAttempt).where(AnswerAttempt.run_task_id.in_(task_ids)))
    session.execute(delete(RunDevice).where(RunDevice.run_id == run.id))
    assignment.version_floor = run.version + 1  # phones drop states older than what they show
    session.delete(run)  # ORM cascade removes run_tasks
    album_blobs: list[str] = []
    album = session.scalar(select(TeamAlbum).where(TeamAlbum.assignment_id == assignment.id))
    if album is not None:
        album_blobs.append(album.blob_name)
        session.delete(album)
    session.flush()
    return blob_names, album_blobs


def delete_photo_blobs(store: BlobStore, container: str, names: list[str]) -> None:
    """Best effort, after commit: a leftover blob is harmless, a lost photo of a live run is not."""
    for name in names:
        try:
            store.delete(container, name)
        except Exception:  # any SDK/network error: log and keep going
            log.exception("could not delete photo blob %s", name)
