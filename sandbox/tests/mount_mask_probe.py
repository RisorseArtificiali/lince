"""Executed inside the disposable mount-mask integration project's sandbox."""

from pathlib import Path

project = Path(__file__).resolve().parent
point = project.parent
alias = point.parent / 'alias'
assert (project / 'inside').read_text() == 'project'
assert not (point / 'sibling/secret').exists()
assert not (alias / 'sibling/secret').exists()
assert point.is_dir() and project.is_dir()
(project / 'persisted').write_text('yes')
(point / 'ephemeral').write_text('yes')
