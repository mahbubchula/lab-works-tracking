from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import bcrypt
import pandas as pd
import streamlit as st

from database import (
    create_goal,
    create_user,
    get_all_goals,
    get_goal_activity,
    get_recent_activity,
    init_db,
    list_goals_for_user,
    log_activity,
    update_goal_status,
    fetch_user_by_email,
)
from groq_client import request_completion

st.set_page_config(page_title="Lab Works Tracker", layout="wide")

STATUS_OPTIONS = [
    "Not started",
    "In progress",
    "Stuck",
    "Waiting for review",
    "Completed",
]
VISIBILITY_OPTIONS = ["public", "private"]

init_db()


def has_groq_key() -> bool:
    if os.getenv("GROQ_API_KEY"):
        return True
    try:
        if "GROQ_API_KEY" in st.secrets:
            return True
        if "groq" in st.secrets and "api_key" in st.secrets["groq"]:
            return True
    except Exception:
        return False
    return False


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def ensure_session_defaults() -> None:
    st.session_state.setdefault("user", None)
    st.session_state.setdefault("goal_title", "")
    st.session_state.setdefault("goal_description", "")
    st.session_state.setdefault("goal_visibility", "public")
    if "goal_due_date" not in st.session_state:
        st.session_state["goal_due_date"] = date.today()


def rerun() -> None:
    """Streamlit renamed experimental_rerun to rerun; support both."""
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def logout() -> None:
    for key in [
        "user",
        "goal_title",
        "goal_description",
        "goal_visibility",
        "goal_due_date",
    ]:
        st.session_state.pop(key, None)
    rerun()


def login_register_panel() -> None:
    st.title("?? Lab Works Tracking Hub")
    st.caption("Set goals, log activities, and let everyone stay aligned.")

    login_tab, register_tab = st.tabs(["Sign in", "Create account"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("School or lab email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in")
            if submitted:
                user = fetch_user_by_email(email)
                if user and verify_password(password, user["password_hash"]):
                    st.session_state["user"] = user
                    st.success("Welcome back! Redirecting...")
                    rerun()
                else:
                    st.error("Invalid credentials")

    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email address")
            role = st.selectbox("Role", ["student", "mentor"], help="Mentors can view all goals")
            password = st.text_input("Create password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            agree = st.checkbox("I will use this tool responsibly")
            submitted = st.form_submit_button("Create my space")
            if submitted:
                if not all([name, email, password]):
                    st.error("Fill out all fields")
                elif password != confirm:
                    st.error("Passwords do not match")
                elif not agree:
                    st.warning("Please confirm the responsibility checkbox")
                else:
                    try:
                        hashed = hash_password(password)
                        user_id = create_user(name, email, role, hashed)
                        st.success("Account created. Sign in on the previous tab.")
                    except sqlite3.IntegrityError:
                        st.warning("That email is already registered.")


def render_workspace(user: Dict[str, Any]) -> None:
    st.title("?? Team workspace")
    st.write(
        f"Logged in as **{user['name']}** — {user['role'].title()} | "
        "Use the tabs below to manage your workflow."
    )
    tabs = st.tabs(["My goals", "Team feed", "Insights & export"])
    with tabs[0]:
        render_goal_creator(user)
        st.divider()
        render_personal_goals(user)
    with tabs[1]:
        render_team_feed(user)
    with tabs[2]:
        render_insights_tab(user)


def render_goal_creator(user: Dict[str, Any]) -> None:
    st.subheader("Create a new goal or experiment milestone")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.session_state.setdefault("goal_title", "")
        title = st.text_input("Goal title", key="goal_title", placeholder="Ex: Validate prototype electrode array")
        description = st.text_area(
            "Description",
            key="goal_description",
            height=150,
            placeholder="Outline why this matters, what success looks like, and deliverables.",
        )
    with col2:
        if st.button("? Polish with Groq", key="goal_ai_btn"):
            if not description.strip():
                st.info("Add a draft description first.")
            else:
                with st.spinner("Groq is drafting..."):
                    polished, error = request_completion(
                        f"Improve this goal description for lab tracking.\n\n{description}",
                        temperature=0.2,
                    )
                if error:
                    st.warning(error)
                elif polished:
                    st.session_state["goal_description"] = polished
                    st.success("Updated with Groq's suggestion")
    col3, col4 = st.columns(2)
    with col3:
        due_date = st.date_input("Target date", key="goal_due_date", value=st.session_state.get("goal_due_date", date.today()))
    with col4:
        visibility = st.selectbox("Visibility", VISIBILITY_OPTIONS, key="goal_visibility")
    status = st.selectbox("Initial status", STATUS_OPTIONS, index=1)
    submit = st.button("Save goal", type="primary")
    if submit:
        if not title.strip():
            st.warning("Give your goal a title.")
            return
        goal_id = create_goal(
            user_id=user["id"],
            title=title,
            description=description,
            due_date=due_date.isoformat() if isinstance(due_date, date) else None,
            status=status,
            visibility=visibility,
        )
        st.success("Goal saved! Scroll below to track it.")
        st.session_state["goal_title"] = ""
        st.session_state["goal_description"] = ""
        st.session_state["goal_visibility"] = "public"
        st.session_state["goal_due_date"] = date.today()
        rerun()


def render_personal_goals(user: Dict[str, Any]) -> None:
    goals = list_goals_for_user(user["id"])
    if not goals:
        st.info("No goals yet. Use the form above to add one.")
        return
    st.subheader("My tracked goals")
    for goal in goals:
        updates_count = goal.get("updates_count", 0)
        header = f"{goal['title']} ({updates_count} updates)"
        with st.expander(header, expanded=False):
            cols = st.columns(3)
            cols[0].metric("Status", goal["status"])
            cols[1].metric("Visibility", goal["visibility"].title())
            due_label = goal["due_date"] or "—"
            cols[2].metric("Target date", due_label)

            status_key = f"status_{goal['id']}"
            new_status = st.selectbox(
                "Update status",
                STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(goal["status"]) if goal["status"] in STATUS_OPTIONS else 0,
                key=status_key,
            )
            if st.button("Apply status", key=f"status_btn_{goal['id']}"):
                update_goal_status(goal["id"], new_status)
                st.success("Status updated")
                rerun()

            render_activity_form(goal, user)
            st.markdown("**Recent log entries**")
            updates = get_goal_activity(goal["id"], limit=5)
            if not updates:
                st.caption("No updates recorded yet.")
            else:
                for update in updates:
                    badge = "AI assisted" if update.get("ai_generated") else ""
                    timestamp = format_timestamp(update["created_at"])
                    st.write(f"• {timestamp} — {update['entry_text']}")
                    if update.get("progress") is not None:
                        st.progress(int(update["progress"]))
                    if badge:
                        st.caption(badge)


def render_activity_form(goal: Dict[str, Any], user: Dict[str, Any]) -> None:
    st.markdown("### Log lab activity")
    key = f"activity_text_{goal['id']}"
    ai_flag_key = f"activity_ai_{goal['id']}"
    st.session_state.setdefault(key, "")
    st.session_state.setdefault(ai_flag_key, False)
    text = st.text_area(
        "Reflection / actions",
        key=key,
        placeholder="Document experiments, blockers, or next steps.",
        height=120,
    )
    slider_key = f"progress_{goal['id']}"
    progress_value = st.slider("Completion %", 0, 100, 25, key=slider_key)
    cols = st.columns(2)
    with cols[0]:
        if st.button("?? Improve text with Groq", key=f"ai_{goal['id']}"):
            if not text.strip():
                st.info("Add a quick note first.")
            else:
                with st.spinner("Groq is helping..."):
                    prompt = (
                        "Rewrite this lab update so it is specific about data, blockers, and next steps.\n\n"
                        f"Goal: {goal['title']}\nUpdate: {text}"
                    )
                    polished, error = request_completion(prompt, temperature=0.25)
                if error:
                    st.warning(error)
                elif polished:
                    st.session_state[key] = polished
                    st.session_state[ai_flag_key] = True
    with cols[1]:
        if st.button("Log activity", key=f"log_{goal['id']}"):
            entry = st.session_state[key].strip()
            if not entry:
                st.warning("Write a short note before saving.")
            else:
                log_activity(
                    goal_id=goal["id"],
                    user_id=user["id"],
                    entry_text=entry,
                    progress=progress_value,
                    ai_generated=st.session_state[ai_flag_key],
                )
                st.session_state[key] = ""
                st.session_state[ai_flag_key] = False
                st.success("Update stored")
                rerun()


def render_team_feed(user: Dict[str, Any]) -> None:
    st.subheader("Live updates from the lab")
    feed = get_recent_activity(limit=40, viewer_id=user["id"], viewer_role=user["role"])
    if not feed:
        st.info("No activity logged yet. Encourage your team to post updates!")
        return
    for item in feed:
        container = st.container(border=True)
        timestamp = format_timestamp(item["created_at"])
        container.markdown(
            f"**{item['user_name']}** {item['user_role']} · {timestamp}  \n"
            f"Goal: *{item['goal_title']}*"
        )
        container.write(item["entry_text"])
        if item.get("progress") is not None:
            container.progress(int(item["progress"]))
        if item.get("ai_generated"):
            container.caption("AI-assisted note")


def render_insights_tab(user: Dict[str, Any]) -> None:
    st.subheader("Analytics & export")
    goals = get_all_goals(viewer_role=user["role"], viewer_id=user["id"])
    if not goals:
        st.info("No goals to summarize yet.")
        return
    df = pd.DataFrame(goals)
    display_cols = [
        "title",
        "status",
        "visibility",
        "due_date",
        "user_name",
        "updates_count",
        "latest_update",
    ]
    rename_map = {
        "title": "Goal",
        "status": "Status",
        "visibility": "Visibility",
        "due_date": "Target",
        "user_name": "Owner",
        "updates_count": "Updates",
        "latest_update": "Last update",
    }
    st.dataframe(
        df[display_cols].rename(columns=rename_map),
        use_container_width=True,
        hide_index=True,
    )
    status_counts = df["status"].value_counts().sort_index()
    st.bar_chart(status_counts)

    upcoming = df[df["due_date"].notna()].copy()
    if not upcoming.empty:
        upcoming["due_date"] = pd.to_datetime(upcoming["due_date"])
        upcoming = upcoming.sort_values("due_date").head(5)
        st.markdown("#### Next deadlines")
        st.table(upcoming[["title", "user_name", "due_date"]])

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download CSV snapshot",
        data=csv,
        file_name="lab_goals_export.csv",
        mime="text/csv",
    )


def format_timestamp(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw).strftime("%d %b %Y · %H:%M")
    except ValueError:
        return raw


def main() -> None:
    ensure_session_defaults()
    with st.sidebar:
        st.header("Lab tracker")
        if st.session_state["user"]:
            user = st.session_state["user"]
            st.markdown(f"**{user['name']}**  \n{user['role'].title()}")
            if st.button("Log out"):
                logout()
            total_goals = len(list_goals_for_user(user["id"]))
            st.metric("My goals", total_goals)
            st.caption("Only mentors can see private student entries.")
            if not has_groq_key():
                st.warning("Add GROQ_API_KEY to enable AI polishing.")
        else:
            st.caption("Sign in to see the dashboard.")
    if st.session_state["user"]:
        render_workspace(st.session_state["user"])
    else:
        login_register_panel()


if __name__ == "__main__":
    main()

