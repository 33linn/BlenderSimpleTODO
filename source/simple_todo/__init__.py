# SPDX-License-Identifier: GPL-3.0-or-later

"""Add a per-file ToDo list to Blender's 3D Viewport sidebar.

The runtime implementation stays in one file so the complete flow remains
easy to follow. Section headers separate each responsibility.
"""

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList


# -----------------------------------------------------------------------------
# Constants and translations
# -----------------------------------------------------------------------------

DATA_BLOCK_NAME = ".simple_todo_data"
STORAGE_MARKER_KEY = "simple_todo_storage_version"
STORAGE_MARKER_VERSION = 1
TRANSLATION_CONTEXT = "ToDo List"
DISPLAY_INCOMPLETE = "INCOMPLETE"
DISPLAY_ALL = "ALL"
TODO_LIST_ID = "SIMPLE_TODO_UL_items"
# Four rows keep the list compact while preserving the full control column.
TODO_LIST_ROWS = 4

# Keep English as the source language and translate only for Japanese UI.
TRANSLATIONS = {
    "ja_JP": {
        ("*", "Completed"): "完了",
        ("*", "Toggle ToDo completion"): "ToDoの完了状態を切り替え",
        (
            "*",
            "Toggle the completion state of this ToDo",
        ): "このToDoの完了状態を切り替えます",
        ("*", "Add ToDo"): "ToDoを追加",
        ("*", "Add the entered text to the ToDo list"): "入力した内容をToDoへ追加します",
        ("*", "Enter a ToDo"): "ToDoを入力してください",
        ("*", "Remove selected ToDo"): "選択中のToDoを削除",
        ("*", "Remove the selected ToDo"): "選択中のToDoを削除します",
        ("*", "Move ToDo"): "ToDoを並べ替え",
        ("*", "Move the selected ToDo up or down"): "選択中のToDoを上または下へ移動します",
        ("*", "Up"): "上",
        ("*", "Move up one position"): "一つ上へ移動",
        ("*", "Down"): "下",
        ("*", "Move down one position"): "一つ下へ移動",
        ("*", "Display"): "表示",
        ("*", "Incomplete Only"): "未完了のみ",
        ("*", "Show only incomplete ToDos"): "未完了のToDoだけを表示します",
        ("*", "All"): "すべて",
        ("*", "Show all ToDos"): "すべてのToDoを表示します",
        ("*", "Search"): "検索",
        ("*", "New ToDo"): "新しいToDo",
        ("*", "ToDo List"): "ToDoリスト",
        (TRANSLATION_CONTEXT, "Add ToDo"): "ToDoを追加",
        (TRANSLATION_CONTEXT, "Add"): "追加",
    }
}


# -----------------------------------------------------------------------------
# Storage and visibility helpers
# -----------------------------------------------------------------------------


def storage_is_marked(storage):
    """Return whether a Text data-block belongs to this extension."""
    return storage.get(STORAGE_MARKER_KEY) == STORAGE_MARKER_VERSION


def get_storage(create=False):
    """Return this file's local Text data-block used for ToDo storage."""
    # The marker keeps the storage discoverable even if Blender or a user
    # changes its display name. Prefer the canonical name when duplicates exist.
    marked_storages = [
        storage
        for storage in bpy.data.texts
        if storage.library is None and storage_is_marked(storage)
    ]
    if marked_storages:
        return next(
            (
                storage
                for storage in marked_storages
                if storage.name == DATA_BLOCK_NAME
            ),
            marked_storages[0],
        )

    # Accept storage created by version 1.0.0 before the marker was added.
    storage = bpy.data.texts.get(DATA_BLOCK_NAME)
    if storage is not None and storage.library is None:
        if create:
            storage[STORAGE_MARKER_KEY] = STORAGE_MARKER_VERSION
        return storage

    if not create:
        return None

    # Text data-blocks and their custom properties are saved in the .blend file.
    storage = bpy.data.texts.new(DATA_BLOCK_NAME)
    storage[STORAGE_MARKER_KEY] = STORAGE_MARKER_VERSION
    return storage


def active_item_is_valid(storage, window_manager):
    """Return whether the active index points to a visible ToDo."""
    index = window_manager.simple_todo_active_index
    if storage is None or not 0 <= index < len(storage.simple_todo_items):
        return False

    return item_is_visible(
        storage.simple_todo_items[index],
        window_manager.simple_todo_display,
        window_manager.simple_todo_search_text,
    )


def item_is_visible(item, display, search_text=""):
    """Return whether an item passes display and text-search filters."""
    if display != DISPLAY_ALL and item.completed:
        return False

    query = search_text.strip().casefold()
    return not query or query in item.text.casefold()


def visible_indices(items, display, search_text=""):
    """Return source indices for the items currently visible in the UI."""
    return [
        index
        for index, item in enumerate(items)
        if item_is_visible(item, display, search_text)
    ]


def ensure_active_item_visible(window_manager, storage=None):
    """Move selection to a visible item after filters or history change."""
    if storage is None:
        storage = get_storage()
    if storage is None:
        window_manager.simple_todo_active_index = -1
        return

    indices = visible_indices(
        storage.simple_todo_items,
        window_manager.simple_todo_display,
        window_manager.simple_todo_search_text,
    )
    active_index = window_manager.simple_todo_active_index
    if active_index in indices:
        return

    # Prefer the next visible item, then fall back to the previous one.
    window_manager.simple_todo_active_index = next(
        (index for index in indices if index >= active_index),
        indices[-1] if indices else -1,
    )


def get_filter_flags(items, display, bitflag, search_text=""):
    """Build the item visibility flags expected by UIList."""
    return [
        bitflag if item_is_visible(item, display, search_text) else 0
        for item in items
    ]


def find_move_target(items, active_index, direction, display, search_text=""):
    """Find an up or down destination based on visible item order."""
    indices = visible_indices(items, display, search_text)
    if active_index not in indices:
        return None

    current_position = indices.index(active_index)
    offset = -1 if direction == "UP" else 1
    target_position = current_position + offset
    if not 0 <= target_position < len(indices):
        return None
    return indices[target_position]


def select_after_removal(window_manager, storage, removed_index):
    """Select a nearby visible item after removal."""
    indices = visible_indices(
        storage.simple_todo_items,
        window_manager.simple_todo_display,
        window_manager.simple_todo_search_text,
    )
    window_manager.simple_todo_active_index = next(
        (index for index in indices if index >= removed_index),
        indices[-1] if indices else -1,
    )


def tag_todo_panels_for_redraw(window_manager):
    """Request a redraw of ToDo panels in every open 3D Viewport."""
    for window in window_manager.windows:
        screen = window.screen
        if screen is None:
            continue

        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


@persistent
def on_history_changed(_scene):
    """Repair non-undoable UI selection after Blender undo or redo."""
    storage = get_storage()
    for window_manager in bpy.data.window_managers:
        ensure_active_item_visible(window_manager, storage)
        tag_todo_panels_for_redraw(window_manager)


# -----------------------------------------------------------------------------
# Shared ToDo addition flow
# -----------------------------------------------------------------------------


def add_todo_text(window_manager, text):
    """Trim and add one ToDo, returning whether addition succeeded."""
    text = text.strip()
    if not text:
        return False

    storage = get_storage(create=True)
    item = storage.simple_todo_items.add()
    item.text = text
    item.completed = False
    window_manager.simple_todo_active_index = (
        len(storage.simple_todo_items) - 1
    )
    # Do not select the new item when the current search hides it.
    ensure_active_item_visible(window_manager, storage)
    # Dialog confirmation does not always invalidate the sidebar by itself.
    tag_todo_panels_for_redraw(window_manager)
    return True


# -----------------------------------------------------------------------------
# Data model and UI-state callbacks
# -----------------------------------------------------------------------------


def on_display_changed(window_manager, _context):
    """Repair selection after switching display mode."""
    ensure_active_item_visible(window_manager)


def on_search_changed(window_manager, _context):
    """Keep selection off items hidden by text search."""
    ensure_active_item_visible(window_manager)


class SIMPLE_TODO_PG_item(PropertyGroup):
    """Minimal data stored in the .blend file for one ToDo."""

    text: StringProperty(name="ToDo", default="")
    completed: BoolProperty(name="Completed", default=False)


# -----------------------------------------------------------------------------
# User actions
# -----------------------------------------------------------------------------


class SIMPLE_TODO_OT_add(Operator):
    bl_idname = "simple_todo.add"
    bl_label = "Add ToDo"
    bl_description = "Add the entered text to the ToDo list"
    bl_options = {"UNDO"}

    text: StringProperty(name="New ToDo", default="")

    def invoke(self, context, _event):
        # A standard dialog delegates text editing, including IME handling,
        # to Blender without using a data-mutating property callback.
        self.text = ""
        return context.window_manager.invoke_props_dialog(
            self,
            width=360,
            title="Add ToDo",
            confirm_text="Add",
            text_ctxt=TRANSLATION_CONTEXT,
        )

    def draw(self, _context):
        # Focus the first field when the dialog opens so typing can start at once.
        self.layout.activate_init = True
        self.layout.prop(self, "text", text="", placeholder="New ToDo")

    def execute(self, context):
        if not add_todo_text(context.window_manager, self.text):
            self.report({"WARNING"}, "Enter a ToDo")
            return {"CANCELLED"}
        return {"FINISHED"}


class SIMPLE_TODO_OT_toggle_completed(Operator):
    bl_idname = "simple_todo.toggle_completed"
    bl_label = "Toggle ToDo completion"
    bl_description = "Toggle the completion state of this ToDo"
    bl_options = {"UNDO"}

    index: IntProperty(options={"HIDDEN"})

    def execute(self, context):
        storage = get_storage()
        if storage is None or not 0 <= self.index < len(
            storage.simple_todo_items
        ):
            return {"CANCELLED"}

        window_manager = context.window_manager
        window_manager.simple_todo_active_index = self.index
        item = storage.simple_todo_items[self.index]
        item.completed = not item.completed
        ensure_active_item_visible(window_manager, storage)
        return {"FINISHED"}


class SIMPLE_TODO_OT_remove(Operator):
    bl_idname = "simple_todo.remove"
    bl_label = "Remove selected ToDo"
    bl_description = "Remove the selected ToDo"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        return active_item_is_valid(get_storage(), context.window_manager)

    def execute(self, context):
        storage = get_storage()
        window_manager = context.window_manager
        if not active_item_is_valid(storage, window_manager):
            return {"CANCELLED"}

        current_index = window_manager.simple_todo_active_index
        storage.simple_todo_items.remove(current_index)
        select_after_removal(window_manager, storage, current_index)
        return {"FINISHED"}


class SIMPLE_TODO_OT_move(Operator):
    bl_idname = "simple_todo.move"
    bl_label = "Move ToDo"
    bl_description = "Move the selected ToDo up or down"
    bl_options = {"UNDO"}

    direction: EnumProperty(
        items=(
            ("UP", "Up", "Move up one position"),
            ("DOWN", "Down", "Move down one position"),
        ),
        options={"HIDDEN"},
    )

    @classmethod
    def poll(cls, context):
        return active_item_is_valid(get_storage(), context.window_manager)

    def execute(self, context):
        storage = get_storage()
        window_manager = context.window_manager
        if not active_item_is_valid(storage, window_manager):
            return {"CANCELLED"}

        current_index = window_manager.simple_todo_active_index
        target_index = find_move_target(
            storage.simple_todo_items,
            current_index,
            self.direction,
            window_manager.simple_todo_display,
            window_manager.simple_todo_search_text,
        )
        if target_index is None:
            return {"CANCELLED"}

        # Move one visible row even when hidden completed items lie between.
        storage.simple_todo_items.move(current_index, target_index)
        window_manager.simple_todo_active_index = target_index
        return {"FINISHED"}


# -----------------------------------------------------------------------------
# 3D Viewport sidebar UI
# -----------------------------------------------------------------------------


class SIMPLE_TODO_UL_items(UIList):
    """Scrollable list with selection, completion, and text filters."""

    def draw_filter(self, context, layout):
        """Draw the search field exposed by Blender's filter toggle."""
        row = layout.row(align=True)
        row.prop(
            context.window_manager,
            "simple_todo_search_text",
            text="",
            placeholder="Search",
            icon="VIEWZOOM",
        )

    def filter_items(self, context, data, property_name):
        items = getattr(data, property_name)
        flags = get_filter_flags(
            items,
            context.window_manager.simple_todo_display,
            self.bitflag_filter_item,
            context.window_manager.simple_todo_search_text,
        )
        return flags, []

    def draw_item(
        self,
        _context,
        layout,
        _data,
        item,
        _icon,
        _active_data,
        _active_property,
        _index,
        _flt_flag,
    ):
        # Persistent changes go through operators so undo remains predictable.
        row = layout.row(align=True)
        toggle = row.operator(
            "simple_todo.toggle_completed",
            text="",
            icon="CHECKBOX_HLT" if item.completed else "CHECKBOX_DEHLT",
            emboss=False,
        )
        toggle.index = _index

        text_row = row.row(align=True)
        text_row.active = not item.completed
        text_row.label(text=item.text)


def draw_display_filter(layout, window_manager):
    """Draw the incomplete-only and all-items display choices."""
    row = layout.row(align=True)
    row.prop(window_manager, "simple_todo_display", expand=True)


def draw_list(layout, storage, window_manager):
    """Draw the list with reorder and removal controls on its right."""
    # Before storage exists, use an unsaved empty collection for display.
    # Opening the panel stays non-destructive and preserves the list height.
    list_data = storage if storage is not None else window_manager
    list_property = (
        "simple_todo_items"
        if storage is not None
        else "simple_todo_empty_items"
    )

    list_row = layout.row()
    list_row.template_list(
        TODO_LIST_ID,
        "",
        list_data,
        list_property,
        window_manager,
        "simple_todo_active_index",
        rows=TODO_LIST_ROWS,
    )

    controls = list_row.column(align=True)
    controls.operator("simple_todo.add", text="", icon="ADD")
    controls.separator()

    active_valid = active_item_is_valid(storage, window_manager)
    active_index = (
        window_manager.simple_todo_active_index if active_valid else -1
    )

    up_target = None
    down_target = None
    if active_valid:
        up_target = find_move_target(
            storage.simple_todo_items,
            active_index,
            "UP",
            window_manager.simple_todo_display,
            window_manager.simple_todo_search_text,
        )
        down_target = find_move_target(
            storage.simple_todo_items,
            active_index,
            "DOWN",
            window_manager.simple_todo_display,
            window_manager.simple_todo_search_text,
        )

    up_row = controls.row(align=True)
    up_row.enabled = up_target is not None
    move_up = up_row.operator("simple_todo.move", text="", icon="TRIA_UP")
    move_up.direction = "UP"

    down_row = controls.row(align=True)
    down_row.enabled = down_target is not None
    move_down = down_row.operator(
        "simple_todo.move",
        text="",
        icon="TRIA_DOWN",
    )
    move_down.direction = "DOWN"

    controls.separator()
    remove_row = controls.row(align=True)
    remove_row.enabled = active_valid
    remove_row.operator("simple_todo.remove", text="", icon="TRASH")


class SIMPLE_TODO_PT_view(Panel):
    """Parent panel in the 3D Viewport sidebar."""

    bl_label = "ToDo List"
    bl_idname = "SIMPLE_TODO_PT_view"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "View"
    bl_order = 0

    def draw(self, context):
        window_manager = context.window_manager
        draw_display_filter(self.layout, window_manager)
        draw_list(self.layout, get_storage(), window_manager)


# -----------------------------------------------------------------------------
# Blender registration lifecycle
# -----------------------------------------------------------------------------

CLASSES = (
    SIMPLE_TODO_PG_item,
    SIMPLE_TODO_OT_add,
    SIMPLE_TODO_OT_toggle_completed,
    SIMPLE_TODO_OT_remove,
    SIMPLE_TODO_OT_move,
    SIMPLE_TODO_UL_items,
    SIMPLE_TODO_PT_view,
)


def register_runtime_properties():
    """Register persistent data and non-persistent UI state."""
    bpy.types.Text.simple_todo_items = CollectionProperty(
        type=SIMPLE_TODO_PG_item,
    )

    # Selection and filters are UI state and are not persisted.
    bpy.types.WindowManager.simple_todo_empty_items = CollectionProperty(
        type=SIMPLE_TODO_PG_item,
        options={"SKIP_SAVE"},
    )
    bpy.types.WindowManager.simple_todo_active_index = IntProperty(
        default=-1,
        options={"SKIP_SAVE"},
    )
    bpy.types.WindowManager.simple_todo_display = EnumProperty(
        name="Display",
        items=(
            (
                DISPLAY_INCOMPLETE,
                "Incomplete Only",
                "Show only incomplete ToDos",
            ),
            (DISPLAY_ALL, "All", "Show all ToDos"),
        ),
        default=DISPLAY_INCOMPLETE,
        update=on_display_changed,
        options={"SKIP_SAVE"},
    )
    bpy.types.WindowManager.simple_todo_search_text = StringProperty(
        name="Search",
        default="",
        update=on_search_changed,
        options={"SKIP_SAVE", "TEXTEDIT_UPDATE"},
    )


def unregister_runtime_properties():
    """Remove registered properties in reverse dependency order."""
    del bpy.types.WindowManager.simple_todo_search_text
    del bpy.types.WindowManager.simple_todo_display
    del bpy.types.WindowManager.simple_todo_active_index
    del bpy.types.WindowManager.simple_todo_empty_items
    del bpy.types.Text.simple_todo_items


def register_history_handlers():
    """Repair UI-only selection after persistent data undo and redo."""
    for handlers in (
        bpy.app.handlers.undo_post,
        bpy.app.handlers.redo_post,
    ):
        if on_history_changed not in handlers:
            handlers.append(on_history_changed)


def unregister_history_handlers():
    """Remove history callbacks without disturbing other add-ons."""
    for handlers in (
        bpy.app.handlers.redo_post,
        bpy.app.handlers.undo_post,
    ):
        while on_history_changed in handlers:
            handlers.remove(on_history_changed)


def register():
    """Register translations, classes, runtime properties, and handlers."""
    bpy.app.translations.register(__name__, TRANSLATIONS)

    for cls in CLASSES:
        bpy.utils.register_class(cls)
    register_runtime_properties()
    register_history_handlers()


def unregister():
    """Unregister in reverse order without leaving Blender definitions."""
    unregister_history_handlers()
    unregister_runtime_properties()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    bpy.app.translations.unregister(__name__)
