"""Run the main functional tests in a background Blender instance."""

import importlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy


project_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_dir / "source"))

simple_todo = importlib.import_module("simple_todo")
simple_todo.register()


# Verify registration, panel placement, translations, and the search UI.
assert hasattr(simple_todo.SIMPLE_TODO_PT_view, "bl_rna")
assert simple_todo.SIMPLE_TODO_PT_view.bl_category == "View"
assert simple_todo.SIMPLE_TODO_PT_view.bl_label == "ToDo List"
assert simple_todo.TRANSLATIONS["ja_JP"][("*", "New ToDo")] == "新しいToDo"
assert simple_todo.TRANSLATIONS["ja_JP"][("*", "ToDo List")] == "ToDoリスト"
add_translation_key = (
    simple_todo.TRANSLATION_CONTEXT,
    "Add",
)
assert simple_todo.TRANSLATIONS["ja_JP"][add_translation_key] == "追加"

# Verify the context-specific translation against Blender's translation API.
preferences_view = bpy.context.preferences.view
original_language = preferences_view.language
original_translate_interface = preferences_view.use_translate_interface
preferences_view.language = "ja_JP"
preferences_view.use_translate_interface = True
assert bpy.app.translations.pgettext_iface(
    "Add",
    simple_todo.TRANSLATION_CONTEXT,
) == "追加"
preferences_view.language = original_language
preferences_view.use_translate_interface = original_translate_interface
assert "draw_filter" in simple_todo.SIMPLE_TODO_UL_items.__dict__
assert bpy.app.background

assert simple_todo.CLASSES == (
    simple_todo.SIMPLE_TODO_PG_item,
    simple_todo.SIMPLE_TODO_OT_add,
    simple_todo.SIMPLE_TODO_OT_toggle_completed,
    simple_todo.SIMPLE_TODO_OT_remove,
    simple_todo.SIMPLE_TODO_OT_move,
    simple_todo.SIMPLE_TODO_UL_items,
    simple_todo.SIMPLE_TODO_PT_view,
)
for operator_class in (
    simple_todo.SIMPLE_TODO_OT_add,
    simple_todo.SIMPLE_TODO_OT_toggle_completed,
    simple_todo.SIMPLE_TODO_OT_remove,
    simple_todo.SIMPLE_TODO_OT_move,
):
    assert "REGISTER" not in operator_class.bl_options
    assert "UNDO" in operator_class.bl_options
assert "on_new_text_committed" not in simple_todo.__dict__

window_manager = bpy.context.window_manager
assert simple_todo.get_storage() is None
assert bpy.data.filepath == ""
assert window_manager.simple_todo_display == "INCOMPLETE"
assert window_manager.simple_todo_search_text == ""
assert len(window_manager.simple_todo_empty_items) == 0


# Verify that the standard dialog requests initial focus for its text field.
class DialogLayout:
    def __init__(self):
        self.activate_init = False
        self.calls = []

    def prop(self, _data, property_name, **kwargs):
        self.calls.append((property_name, kwargs))


dialog_layout = DialogLayout()
dialog_owner = SimpleNamespace(layout=dialog_layout, text="")
simple_todo.SIMPLE_TODO_OT_add.draw(dialog_owner, None)
assert dialog_layout.activate_init
assert dialog_layout.calls == [
    ("text", {"text": "", "placeholder": "New ToDo"})
]


class DialogWindowManager:
    def __init__(self):
        self.arguments = None

    def invoke_props_dialog(self, _operator, **kwargs):
        self.arguments = kwargs
        return {"RUNNING_MODAL"}


dialog_window_manager = DialogWindowManager()
dialog_context = SimpleNamespace(window_manager=dialog_window_manager)
dialog_owner.text = "stale draft"
assert simple_todo.SIMPLE_TODO_OT_add.invoke(
    dialog_owner,
    dialog_context,
    None,
) == {"RUNNING_MODAL"}
assert dialog_owner.text == ""
assert dialog_window_manager.arguments["confirm_text"] == "Add"
assert dialog_window_manager.arguments["text_ctxt"] == (
    simple_todo.TRANSLATION_CONTEXT
)


# Redraw only 3D Viewports, where the ToDo panel can be displayed.
class RedrawArea:
    def __init__(self, area_type):
        self.type = area_type
        self.redraw_count = 0

    def tag_redraw(self):
        self.redraw_count += 1


view_area = RedrawArea("VIEW_3D")
text_area = RedrawArea("TEXT_EDITOR")
redraw_window_manager = SimpleNamespace(
    windows=[
        SimpleNamespace(
            screen=SimpleNamespace(areas=[view_area, text_area]),
        ),
        SimpleNamespace(screen=None),
    ],
)
simple_todo.tag_todo_panels_for_redraw(redraw_window_manager)
assert view_area.redraw_count == 1
assert text_area.redraw_count == 0


# Add items through the operator and verify trimming and empty input handling.
redraw_requests = []
original_redraw = simple_todo.tag_todo_panels_for_redraw
simple_todo.tag_todo_panels_for_redraw = redraw_requests.append
try:
    for text in ("  UVを修正  ", "ウェイト調整", "サムネイル撮影"):
        assert bpy.ops.simple_todo.add(text=text) == {"FINISHED"}
finally:
    simple_todo.tag_todo_panels_for_redraw = original_redraw

assert redraw_requests == [window_manager, window_manager, window_manager]

storage = simple_todo.get_storage()
assert [item.text for item in storage.simple_todo_items] == [
    "UVを修正",
    "ウェイト調整",
    "サムネイル撮影",
]
assert storage[simple_todo.STORAGE_MARKER_KEY] == (
    simple_todo.STORAGE_MARKER_VERSION
)
assert bpy.ops.simple_todo.add(text="   ") == {"CANCELLED"}
assert len(storage.simple_todo_items) == 3

# Migrate unmarked 1.0.0 storage and find marked storage after a rename.
del storage[simple_todo.STORAGE_MARKER_KEY]
assert simple_todo.get_storage() is storage
assert simple_todo.get_storage(create=True) is storage
assert storage[simple_todo.STORAGE_MARKER_KEY] == (
    simple_todo.STORAGE_MARKER_VERSION
)
storage.name = ".renamed_simple_todo_data"
assert simple_todo.get_storage() is storage


# Draw item text as a label and do not expose in-place text editing.
class RecordingLayout:
    def __init__(self):
        self.calls = []
        self.active = True

    def row(self, **_kwargs):
        return self

    def column(self, **_kwargs):
        return self

    def template_list(self, *_args, **kwargs):
        self.calls.append(("template_list", kwargs))

    def separator(self):
        self.calls.append(("separator", None))

    def prop(self, _data, property_name, **_kwargs):
        self.calls.append(("prop", property_name))

    def operator(self, operator_id, **_kwargs):
        self.calls.append(("operator", operator_id))
        return SimpleNamespace()

    def label(self, **kwargs):
        self.calls.append(("label", kwargs.get("text")))


recording_layout = RecordingLayout()
simple_todo.SIMPLE_TODO_UL_items.draw_item(
    None,
    None,
    recording_layout,
    storage,
    storage.simple_todo_items[0],
    0,
    window_manager,
    "simple_todo_active_index",
    0,
    0,
)
assert (
    "operator",
    "simple_todo.toggle_completed",
) in recording_layout.calls
assert ("label", "UVを修正") in recording_layout.calls
assert ("prop", "completed") not in recording_layout.calls
assert ("prop", "text") not in recording_layout.calls

# Keep the compact Add button at the top of the list's control column.
list_layout = RecordingLayout()
simple_todo.draw_list(list_layout, storage, window_manager)
assert ("template_list", {"rows": simple_todo.TODO_LIST_ROWS}) in (
    list_layout.calls
)
assert simple_todo.TODO_LIST_ROWS == 4
operator_calls = [
    call for call in list_layout.calls if call[0] == "operator"
]
assert operator_calls[0] == ("operator", "simple_todo.add")


# The dialog's confirmation and direct operator calls share the same execute path.
assert bpy.ops.simple_todo.add(text="ダイアログで追加") == {"FINISHED"}
assert [item.text for item in storage.simple_todo_items][-1] == "ダイアログで追加"


# Toggle completion through an undoable operator and repair hidden selection.
window_manager.simple_todo_active_index = 1
assert bpy.ops.simple_todo.toggle_completed(index=1) == {"FINISHED"}
assert storage.simple_todo_items[1].completed
assert window_manager.simple_todo_active_index == 2

flags = simple_todo.get_filter_flags(
    storage.simple_todo_items,
    window_manager.simple_todo_display,
    1,
)
assert [bool(flag) for flag in flags] == [True, False, True, True]

window_manager.simple_todo_display = "ALL"
flags = simple_todo.get_filter_flags(
    storage.simple_todo_items,
    window_manager.simple_todo_display,
    1,
)
assert [bool(flag) for flag in flags] == [True, True, True, True]

# Apply search and completion filters together and repair the selection.
window_manager.simple_todo_active_index = 2
window_manager.simple_todo_search_text = "UV"
search_flags = simple_todo.get_filter_flags(
    storage.simple_todo_items,
    window_manager.simple_todo_display,
    1,
    window_manager.simple_todo_search_text,
)
assert [bool(flag) for flag in search_flags] == [True, False, False, False]
assert window_manager.simple_todo_active_index == 0

# Do not select a newly added item when the current search hides it.
assert simple_todo.add_todo_text(window_manager, "検索外")
assert window_manager.simple_todo_active_index == 0
storage.simple_todo_items.remove(len(storage.simple_todo_items) - 1)

# Require both conditions when search and incomplete-only mode are active.
window_manager.simple_todo_display = "INCOMPLETE"
window_manager.simple_todo_search_text = "ウェイト"
combined_flags = simple_todo.get_filter_flags(
    storage.simple_todo_items,
    window_manager.simple_todo_display,
    1,
    window_manager.simple_todo_search_text,
)
assert [bool(flag) for flag in combined_flags] == [False, False, False, False]
window_manager.simple_todo_search_text = ""


# Reorder by one visible row, skipping completed items hidden by the filter.
window_manager.simple_todo_active_index = 2
window_manager.simple_todo_display = "INCOMPLETE"
assert bpy.ops.simple_todo.move(direction="UP") == {"FINISHED"}
assert [item.text for item in storage.simple_todo_items][:3] == [
    "サムネイル撮影",
    "UVを修正",
    "ウェイト調整",
]

assert bpy.ops.simple_todo.remove() == {"FINISHED"}
assert [item.text for item in storage.simple_todo_items][:2] == [
    "UVを修正",
    "ウェイト調整",
]
assert window_manager.simple_todo_active_index == 0


# Verify that the Text data-block follows .blend save and reload behavior.
persistence_path = (
    Path(tempfile.gettempdir()) / "simple_todo_persistence.blend"
)
empty_path = Path(tempfile.gettempdir()) / "simple_todo_empty.blend"
second_scene = bpy.data.scenes.new("SimpleToDoSecondScene")
assert simple_todo.get_storage() is storage
assert len(second_scene.objects) == 0

expected_saved_texts = [item.text for item in storage.simple_todo_items]
expected_storage_name = storage.name
bpy.ops.wm.save_as_mainfile(filepath=str(persistence_path))
bpy.data.texts.remove(storage)
assert simple_todo.get_storage() is None
bpy.ops.wm.save_as_mainfile(filepath=str(empty_path))

bpy.ops.wm.open_mainfile(filepath=str(persistence_path))
assert [
    item.text for item in simple_todo.get_storage().simple_todo_items
] == expected_saved_texts
assert simple_todo.get_storage().name == expected_storage_name
assert simple_todo.storage_is_marked(simple_todo.get_storage())

bpy.ops.wm.open_mainfile(filepath=str(empty_path))
assert simple_todo.get_storage() is None

bpy.ops.wm.open_mainfile(filepath=str(persistence_path))
assert simple_todo.get_storage() is not None

simple_todo.unregister()
assert not hasattr(bpy.types.WindowManager, "simple_todo_display")
assert not hasattr(bpy.types.WindowManager, "simple_todo_search_text")
assert not hasattr(bpy.types.WindowManager, "simple_todo_empty_items")
assert not hasattr(bpy.types.WindowManager, "simple_todo_new_text")
print("SIMPLE_TODO_TEST_OK")
