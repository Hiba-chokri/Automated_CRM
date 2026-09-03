import os

import psycopg2
import psycopg2.extras
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "dbname": os.getenv("POSTGRES_DB"),
}
APPROVAL_SECRET = os.getenv("APPROVAL_SECRET")
IMEJIS_API_KEY = os.getenv("IMEJIS_API_KEY")


@st.cache_data(ttl=300)
def fetch_image_bytes(image_url):
    try:
        resp = requests.get(
            image_url, headers={"dma-api-key": IMEJIS_API_KEY}, timeout=10
        )
        if resp.status_code == 200:
            return resp.content
    except requests.RequestException:
        pass
    return None

st.set_page_config(page_title="Daba.Cities Content Approval", layout="wide")
st.title("Content Approval Dashboard")


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def fetch_pending_posts():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, notion_id, content_type, resume_url, created_at
                FROM posts
                WHERE status = 'pending_approval'
                ORDER BY created_at ASC
                """
            )
            return cur.fetchall()


def fetch_variants(post_id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT platform, text, image_url
                FROM post_variants
                WHERE post_id = %s
                ORDER BY platform
                """,
                (post_id,),
            )
            return cur.fetchall()


def send_decision(resume_url, decision, edits=None, feedback=None):
    payload = {"decision": decision}
    if edits:
        payload["edits"] = edits
    if feedback:
        payload["feedback"] = feedback
    response = requests.post(
        resume_url,
        headers={
            "X-Approval-Secret": APPROVAL_SECRET,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )
    return response


posts = fetch_pending_posts()

if not posts:
    st.info("No posts pending review.")

for post in posts:
    with st.container(border=True):
        st.subheader(f"{post['content_type']} — post #{post['id']}")
        st.caption(f"Notion ID: {post['notion_id']} • Created: {post['created_at']}")

        edit_mode_key = f"edit_mode_{post['id']}"
        if edit_mode_key not in st.session_state:
            st.session_state[edit_mode_key] = False

        reject_mode_key = f"reject_mode_{post['id']}"
        if reject_mode_key not in st.session_state:
            st.session_state[reject_mode_key] = False

        variants = fetch_variants(post["id"])
        cols = st.columns(len(variants)) if variants else []
        edited_texts = {}
        for col, variant in zip(cols, variants):
            with col:
                st.markdown(f"**{variant['platform'].capitalize()}**")
                if variant["image_url"]:
                    image_bytes = fetch_image_bytes(variant["image_url"])
                    if image_bytes:
                        st.image(image_bytes)
                    else:
                        st.caption("(image unavailable)")
                if st.session_state[edit_mode_key]:
                    edited_texts[variant["platform"]] = st.text_area(
                        "Text",
                        value=variant["text"],
                        key=f"text_{post['id']}_{variant['platform']}",
                        label_visibility="collapsed",
                    )
                else:
                    st.write(variant["text"])

        st.divider()

        if st.session_state[edit_mode_key]:
            save_col, cancel_col = st.columns(2)
            with save_col:
                if st.button("Save Edits", key=f"save_{post['id']}", type="primary"):
                    if not post["resume_url"]:
                        st.error("No resume URL saved for this post yet.")
                    else:
                        resp = send_decision(
                            post["resume_url"], "quick_edit", edits=edited_texts
                        )
                        if resp.status_code == 200:
                            st.session_state[edit_mode_key] = False
                            st.success("Edits sent — refresh to update the list.")
                        else:
                            st.error(f"Failed ({resp.status_code}): {resp.text}")
            with cancel_col:
                if st.button("Cancel", key=f"cancel_{post['id']}"):
                    st.session_state[edit_mode_key] = False
        elif st.session_state[reject_mode_key]:
            feedback_text = st.text_area(
                "Why is this being rejected? (visible to the content creator)",
                key=f"feedback_{post['id']}",
            )
            send_col, cancel_col = st.columns(2)
            with send_col:
                if st.button("Send Rejection", key=f"sendreject_{post['id']}", type="primary"):
                    if not feedback_text.strip():
                        st.error("Please add a reason before sending.")
                    elif not post["resume_url"]:
                        st.error("No resume URL saved for this post yet.")
                    else:
                        resp = send_decision(
                            post["resume_url"], "reject", feedback=feedback_text
                        )
                        if resp.status_code == 200:
                            st.session_state[reject_mode_key] = False
                            st.success("Rejection sent — refresh to update the list.")
                        else:
                            st.error(f"Failed ({resp.status_code}): {resp.text}")
            with cancel_col:
                if st.button("Cancel", key=f"cancelreject_{post['id']}"):
                    st.session_state[reject_mode_key] = False
        else:
            button_cols = st.columns(4)
            actions = [
                ("Approve", "approved", "primary"),
                ("Rewrite", "rewrite", "secondary"),
                ("Redo Design", "redo_design", "secondary"),
            ]
            for col, (label, decision, button_type) in zip(button_cols, actions):
                with col:
                    if st.button(label, key=f"{decision}_{post['id']}", type=button_type):
                        if not post["resume_url"]:
                            st.error("No resume URL saved for this post yet.")
                        else:
                            resp = send_decision(post["resume_url"], decision)
                            if resp.status_code == 200:
                                st.success(f"Sent '{decision}' — refresh to update the list.")
                            else:
                                st.error(f"Failed ({resp.status_code}): {resp.text}")
            with button_cols[3]:
                if st.button("Reject", key=f"rejectbtn_{post['id']}"):
                    st.session_state[reject_mode_key] = True
                    st.rerun()
            if st.button("Edit", key=f"editbtn_{post['id']}"):
                st.session_state[edit_mode_key] = True
                st.rerun()
