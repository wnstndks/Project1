"""Study-page lessons (D-034): static, structured investing lessons.

Pure data. No DB, no network, no pandas. The model lives in `model.py`, the ordered
catalog in `catalog.py`, and each lesson in its own `content/<id>.py` file so a long lesson
can be saved and tested on its own. Every string is checked against the shared banned-word
and grading-word patterns at construction time; the catalog cannot import a lesson that
promises returns or grades the reader.
"""
