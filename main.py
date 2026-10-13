import asyncio
import uuid

import flet as ft

from storage import (
    clear_session,
    legacy_tasks_migrated,
    load_legacy_tasks,
    load_session,
    mark_legacy_tasks_migrated,
    save_session,
)
from supabase_api import SupabaseClient, SupabaseError


STATUSES = ["TODO", "INPROGRESS", "DONE"]


class Task(ft.Column):
    def __init__(self, record, on_change, on_delete):
        super().__init__()
        self.task_id = record["id"]
        self.task_name = record["title"]
        self.status = record["status"] if record["status"] in STATUSES else "TODO"
        self.on_change = on_change
        self.on_delete = on_delete

    def build(self):
        self.status_picker = ft.Dropdown(
            value=self.status,
            options=[ft.DropdownOption(text=status) for status in STATUSES],
            on_select=self.status_changed,
            width=160,
        )
        self.edit_name = ft.TextField(expand=1)
        self.display_name = ft.Text(self.task_name, expand=True)
        self.display_view = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.display_name,
                self.status_picker,
                ft.Row(
                    spacing=0,
                    controls=[
                        ft.IconButton(
                            icon=ft.Icons.CREATE_OUTLINED,
                            tooltip="Edit task",
                            on_click=self.edit_clicked,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip="Delete task",
                            on_click=self.delete_clicked,
                        ),
                    ],
                ),
            ],
        )
        self.edit_view = ft.Row(
            visible=False,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self.edit_name,
                ft.IconButton(
                    icon=ft.Icons.DONE_OUTLINE_OUTLINED,
                    icon_color=ft.Colors.GREEN,
                    tooltip="Save task",
                    on_click=self.save_clicked,
                ),
            ],
        )
        self.controls = [self.display_view, self.edit_view]

    def edit_clicked(self, e):
        self.edit_name.value = self.task_name
        self.display_view.visible = False
        self.edit_view.visible = True
        self.update()

    async def save_clicked(self, e):
        new_name = (self.edit_name.value or "").strip()
        self.display_view.visible = True
        self.edit_view.visible = False
        if new_name:
            self.task_name = new_name
            self.display_name.value = new_name
            await self.on_change(self)
        else:
            self.update()

    async def status_changed(self, e):
        self.status = e.control.value
        await self.on_change(self)

    async def delete_clicked(self, e):
        await self.on_delete(self)


class TodoApp(ft.Column):
    def __init__(self, preferences):
        super().__init__()
        self.preferences = preferences
        self.client = None
        self.session = None
        self.user = None
        self.config_error = None
        try:
            self.client = SupabaseClient()
        except SupabaseError as error:
            self.config_error = str(error)

    def build(self):
        self.width = 600
        self.email_field = ft.TextField(label="Email", keyboard_type=ft.KeyboardType.EMAIL)
        self.password_field = ft.TextField(
            label="Password", password=True, can_reveal_password=True
        )
        self.message = ft.Text("")
        self._show_login()

    def _show_login(self, message=""):
        setup_controls = []
        if self.config_error:
            setup_controls = [
                
            ]
        self.message.value = message
        self.controls = [
            ft.Text("Sign in to sync your tasks"),
            *setup_controls,
            self.email_field,
            self.password_field,
            ft.Row(
                controls=[
                    ft.Button(content="Sign in", on_click=self.sign_in_clicked),
                    ft.OutlinedButton(content="Create account", on_click=self.sign_up_clicked),
                ],
            ),
            self.message,
        ]
        if self.page:
            self.update()

    async def sign_in_clicked(self, e):
        await self._authenticate(create_account=False)

    async def sign_up_clicked(self, e):
        await self._authenticate(create_account=True)

    async def _authenticate(self, create_account):
        if not self.client:
            self._show_login(self.config_error or "Supabase is not configured.")
            return
        email = (self.email_field.value or "").strip()
        password = self.password_field.value or ""
        if not email or not password:
            self._show_login("Enter your email and password.")
            return
        self.message.value = "Connecting…"
        self.update()
        try:
            if create_account:
                result = await self.client.sign_up(email, password)
                if not result.get("access_token"):
                    self._show_login("Account created. Confirm your email, then sign in.")
                    return
            else:
                result = await self.client.sign_in(email, password)
            await self._activate_session(result)
        except Exception as error:
            self._show_login(str(error))

    async def _activate_session(self, session):
        user = session.get("user")
        if not user:
            user = await self.client.get_user(session["access_token"])
            session["user"] = user
        self.session = session
        self.user = user
        await save_session(self.preferences, session)
        await self._load_task_list()

    async def restore_session(self):
        if not self.client:
            return
        saved = await load_session(self.preferences)
        if not saved or not saved.get("refresh_token"):
            return
        try:
            refreshed = await self.client.refresh_session(saved["refresh_token"])
            refreshed["user"] = refreshed.get("user") or saved.get("user")
            await self._activate_session(refreshed)
        except Exception as error:
            self._show_login(f"Couldn't restore this session. Please sign in: {error}")

    async def _load_task_list(self):
        access_token = self.session["access_token"]
        records = await self.client.list_tasks(access_token)
        if not await legacy_tasks_migrated(self.preferences):
            old_tasks = await load_legacy_tasks(self.preferences)
            if not records and old_tasks:
                imports = []
                for item in old_tasks:
                    if not isinstance(item, dict):
                        continue
                    title = (item.get("name") or item.get("title") or "").strip()
                    if not title:
                        continue
                    status = item.get("status", "TODO")
                    if status not in STATUSES:
                        status = "DONE" if item.get("completed") else "TODO"
                    imports.append({
                        "id": str(uuid.uuid4()),
                        "user_id": self.user["id"],
                        "title": title,
                        "status": status,
                    })
                if imports:
                    records = await self.client.import_tasks(access_token, imports)
            await mark_legacy_tasks_migrated(self.preferences)
        self._show_tasks(records)

    def _show_tasks(self, records):
        self.task_list = ft.Column(
            controls=[Task(record, self.update_task, self.delete_task) for record in records]
        )
        self.filter = ft.TabBar(
            scrollable=False,
            tabs=[ft.Tab(label="all"), ft.Tab(label="active"), ft.Tab(label="completed")],
        )
        self.filter_tabs = ft.Tabs(
            length=3,
            selected_index=0,
            on_change=lambda e: self.update(),
            content=self.filter,
        )
        self.items_left = ft.Text("0 active items left")
        self.new_task = ft.TextField(
            hint_text="What needs to be done?",
            on_submit=self.add_task,
            expand=True,
        )
        self.message = ft.Text("")
        self.controls = [
            ft.Row(
                controls=[
                    ft.Text(f"Tasks for {self.user.get('email', '')}"),
                    ft.TextButton(content="Sign out", on_click=self.sign_out_clicked),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            ft.Row(
                controls=[
                    self.new_task,
                    ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=self.add_task),
                ],
            ),
            self.filter_tabs,
            self.task_list,
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    self.items_left,
                    ft.OutlinedButton(content="Clear completed", on_click=self.clear_completed),
                ],
            ),
            self.message,
        ]
        self.update()

    async def add_task(self, e):
        title = (self.new_task.value or "").strip()
        if not title:
            return
        try:
            rows = await self.client.create_task(
                self.session["access_token"], str(uuid.uuid4()), self.user["id"], title, "TODO"
            )
            self.task_list.controls.append(Task(rows[0], self.update_task, self.delete_task))
            self.new_task.value = ""
            self.update()
            await self.new_task.focus()
        except Exception as error:
            self._show_task_error(error)

    async def update_task(self, task):
        try:
            await self.client.update_task(
                self.session["access_token"], task.task_id, task.task_name, task.status
            )
            self.update()
        except Exception as error:
            await self._reload_after_error(error)

    async def delete_task(self, task):
        try:
            await self.client.delete_task(self.session["access_token"], task.task_id)
            self.task_list.controls.remove(task)
            self.update()
        except Exception as error:
            self._show_task_error(error)

    async def clear_completed(self, e):
        completed = [task for task in self.task_list.controls if task.status == "DONE"]
        try:
            for task in completed:
                await self.client.delete_task(self.session["access_token"], task.task_id)
            self.task_list.controls = [
                task for task in self.task_list.controls if task.status != "DONE"
            ]
            self.update()
        except Exception as error:
            await self._reload_after_error(error)

    async def _reload_after_error(self, error):
        try:
            records = await self.client.list_tasks(self.session["access_token"])
            self._show_tasks(records)
            self.message.value = str(error)
            self.update()
        except Exception:
            self._show_task_error(error)

    def _show_task_error(self, error):
        self.message.value = str(error)
        self.update()

    async def sign_out_clicked(self, e):
        try:
            await self.client.sign_out(self.session["access_token"])
        except Exception:
            pass
        await clear_session(self.preferences)
        self.session = None
        self.user = None
        self._show_login("Signed out.")

    def before_update(self):
        if not hasattr(self, "task_list"):
            return
        selected = self.filter.tabs[self.filter_tabs.selected_index].label
        active_count = 0
        for task in self.task_list.controls:
            task.visible = (
                selected == "all"
                or (selected == "active" and task.status != "DONE")
                or (selected == "completed" and task.status == "DONE")
            )
            if task.status != "DONE":
                active_count += 1
        self.items_left.value = f"{active_count} active item(s) left"


async def main(page: ft.Page):
    page.title = "ToDo App"
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.scroll = ft.ScrollMode.ADAPTIVE
    preferences = ft.SharedPreferences()
    app = TodoApp(preferences)
    page.add(ft.SafeArea(content=app))
    asyncio.create_task(app.restore_session())


if __name__ == "__main__":
    ft.run(main)
