import httpx


SUPABASE_URL = "https://kqlauxfgdnbhyjwjzcmy.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxbGF1eGZnZG5iaHlqd2p6Y215Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE5MDIwODcsImV4cCI6MjEwNzQ3ODA4N30.BefzQxo_T2Ql1o0VMembUl5WoeAs52F6QsIbSL8Oi4M"


class SupabaseError(Exception):
    pass


class SupabaseClient:
    def __init__(self):
        self.base_url = "https://kqlauxfgdnbhyjwjzcmy.supabase.co".rstrip("/")
        self.anon_key = SUPABASE_ANON_KEY


    def headers(self, access_token=None):
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {access_token or self.anon_key}",
            "Content-Type": "application/json",
        }

    async def request(self, method, path, *, token=None, params=None, body=None, prefer=None):
        headers = self.headers(token)
        if prefer:
            headers["Prefer"] = prefer
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                params=params,
                json=body,
            )
        if response.status_code >= 400:
            try:
                details = response.json()
                message = (
                    details.get("msg")
                    or details.get("message")
                    or details.get("error_description")
                    or details.get("error")
                )
            except Exception:
                message = response.text
            raise SupabaseError(message or f"Supabase request failed ({response.status_code}).")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def sign_in(self, email, password):
        return await self.request(
            "POST", "/auth/v1/token", params={"grant_type": "password"},
            body={"email": email, "password": password},
        )

    async def sign_up(self, email, password):
        return await self.request(
            "POST", "/auth/v1/signup",
            body={"email": email, "password": password},
        )

    async def refresh_session(self, refresh_token):
        return await self.request(
            "POST", "/auth/v1/token", params={"grant_type": "refresh_token"},
            body={"refresh_token": refresh_token},
        )

    async def get_user(self, access_token):
        return await self.request("GET", "/auth/v1/user", token=access_token)

    async def sign_out(self, access_token):
        await self.request("POST", "/auth/v1/logout", token=access_token)

    async def list_tasks(self, access_token):
        return await self.request(
            "GET", "/rest/v1/tasks",
            token=access_token,
            params={"select": "id,title,status", "order": "created_at.asc"},
        )

    async def create_task(self, access_token, task_id, user_id, title, status):
        return await self.request(
            "POST", "/rest/v1/tasks", token=access_token,
            body={"id": task_id, "user_id": user_id, "title": title, "status": status},
            prefer="return=representation",
        )

    async def import_tasks(self, access_token, records):
        return await self.request(
            "POST", "/rest/v1/tasks", token=access_token,
            body=records,
            prefer="return=representation",
        )

    async def update_task(self, access_token, task_id, title, status):
        await self.request(
            "PATCH", "/rest/v1/tasks", token=access_token,
            params={"id": f"eq.{task_id}"},
            body={"title": title, "status": status},
        )

    async def delete_task(self, access_token, task_id):
        await self.request(
            "DELETE", "/rest/v1/tasks", token=access_token,
            params={"id": f"eq.{task_id}"},
        )
