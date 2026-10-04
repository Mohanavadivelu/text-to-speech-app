from contextlib import contextmanager


@contextmanager
def single_undo_step(text):
    """Group edits so one Ctrl+Z undoes them all.

    Tk's autoseparators add an undo boundary whenever an edit switches between
    delete and insert, so a replace (delete + insert) would otherwise take
    several Ctrl+Z presses to undo.
    """
    auto = text.cget("autoseparators")
    text.edit_separator()
    text.configure(autoseparators=False)
    try:
        yield
    finally:
        text.edit_separator()
        text.configure(autoseparators=auto)
