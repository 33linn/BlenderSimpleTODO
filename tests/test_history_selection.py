"""Verify selection repair around Blender's undo/redo boundary."""

import importlib
import sys
from pathlib import Path

import bpy


project_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_dir / "source"))

simple_todo = importlib.import_module("simple_todo")
simple_todo.register()

assert simple_todo.on_history_changed in bpy.app.handlers.undo_post
assert simple_todo.on_history_changed in bpy.app.handlers.redo_post

window_manager = bpy.context.window_manager
for text in ("Visible before", "Hidden completed", "Visible after"):
    assert bpy.ops.simple_todo.add(text=text) == {"FINISHED"}

storage = simple_todo.get_storage()
storage.simple_todo_items[1].completed = True
window_manager.simple_todo_display = "INCOMPLETE"
window_manager.simple_todo_search_text = ""

# WindowManager data is not restored by Blender's memfile undo. Reproduce the
# stale selection left after a removed item is restored before undo_post runs.
window_manager.simple_todo_active_index = 1
assert not simple_todo.active_item_is_valid(storage, window_manager)
assert not bpy.ops.simple_todo.remove.poll()

simple_todo.on_history_changed(None)
assert window_manager.simple_todo_active_index == 2
assert simple_todo.active_item_is_valid(storage, window_manager)

# An undone addition can also leave the selection beyond the restored list.
window_manager.simple_todo_active_index = len(storage.simple_todo_items)
simple_todo.on_history_changed(None)
assert window_manager.simple_todo_active_index == 2

simple_todo.unregister()
assert simple_todo.on_history_changed not in bpy.app.handlers.undo_post
assert simple_todo.on_history_changed not in bpy.app.handlers.redo_post
print("SIMPLE_TODO_HISTORY_TEST_OK")
