import streamlit as st
import json
import os
import google.generativeai as genai
from collections import defaultdict
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid
from fuzzywuzzy import fuzz

st.set_page_config(page_title="AI-Powered Data Science Portfolio", layout="wide")


st.markdown("""
<style>
/* Main Title */
h1 {
    font-size: 52px !important;
    font-weight: 800 !important;
}

/* Section Headings (e.g. st.markdown(\"### ...\")) */
h3 {
    font-size: 36px !important;
    font-weight: 600 !important;
}

/* TextInput label and input text */
label, .stTextInput label {
    font-size: 28px !important;
    font-weight: bold !important;
}
.stTextInput input {
    font-size: 18px !important;
}

/* SelectBox */
.stSelectbox label {
    font-size: 28px !important;
    font-weight: bold !important;
}
.css-1wa3eu0-placeholder {  /* dropdown placeholder */
    font-size: 18px !important;
}
.css-1uccc91-singleValue {  /* selected value */
    font-size: 18px !important;
}

/* Buttons */
.stButton button {
    font-size: 18px !important;
    padding: 8px 16px;
    font-weight: bold;
}

/* Markdown paragraph custom */
p.main-text {
    font-size: 22px !important;
    font-weight: 600;
    color: #444;
}

/* Rating section note */
.rating-tooltip {
    font-size: 16px;
    font-style: italic;
    color: #999;
}
.ai-idea-frame {
    background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
    border-radius: 16px;
    padding: 20px;
    margin-top: 30px;
    box-shadow: 0 8px 20px rgba(37, 117, 252, 0.4);
    color: white;
    font-weight: 600;
    border: 3px solid #fff;
}
.ai-idea-frame h2 {
    margin-top: 0;
    margin-bottom: 10px;
}
.ai-idea-frame p {
    font-size: 18px;
    margin-bottom: 15px;
}
</style>
""", unsafe_allow_html=True)


GOOGLE_API_KEY = (os.getenv('GOOGLE_API_KEY') or st.secrets.get("GOOGLE_API_KEY"))
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash-latest")


SHEET_NAME = "Portfolio_Interactions"

rating_tooltips = {
    0: "No Rating",
    1: "⭐ - Poor",
    2: "⭐⭐ - Fair",
    3: "⭐⭐⭐ - Good",
    4: "⭐⭐⭐⭐ - Very Good",
    5: "⭐⭐⭐⭐⭐ - Excellent"
}

rating_emojis = {
    0: "✖️",
    1: "⭐",
    2: "⭐⭐",
    3: "⭐⭐⭐",
    4: "⭐⭐⭐⭐",
    5: "⭐⭐⭐⭐⭐"
}

def get_gsheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet

def upsert_gsheet(project_title, is_favorite, rating):
    try:
        sheet = get_gsheet()
        all_data = sheet.get_all_values()
        headers = all_data[0]
        rows = all_data[1:]
        user_id = st.session_state.get("user_id", "anonymous")

        for idx, row in enumerate(rows, start=2):
            if row[1] == user_id and row[2] == project_title:
                sheet.update(f"A{idx}:E{idx}", [[
                    datetime.now().isoformat(), user_id, project_title,
                    "Yes" if is_favorite else "No", rating
                ]])
                return

        sheet.append_row([
            datetime.now().isoformat(), user_id, project_title,
            "Yes" if is_favorite else "No", rating
        ])

    except Exception as e:
        st.error(f"❌ Failed to update Google Sheet: {e}")

@st.cache_data
def load_projects():
    with open("projects.json", "r", encoding="utf-8") as f:
        return json.load(f)

def extract_topics_from_text(user_text):
    prompt = f"""
    Based on the user's message below, suggest the 3 most relevant topic tags (e.g., health, NLP, visualization).
    Output the tags in a single line, separated by commas only.

    User message: "{user_text}"
    Tags:
    """
    response = model.generate_content(prompt)
    tags_text = response.text.strip()
    tags = [tag.strip().lower() for tag in tags_text.split(",")]
    return tags

def get_categories(projects):
    categories = set()
    for proj in projects:
        for tag in proj["tags"]:
            categories.add(tag)
    return sorted(categories)

def init_session():
    if "favorites" not in st.session_state:
        st.session_state.favorites = set()
    if "ratings" not in st.session_state:
        st.session_state.ratings = {}
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())

st.title("📊 AI-Powered Portfolio")
st.markdown("<p style='font-size: 24px;'>Discover my projects based on your interests</p>", unsafe_allow_html=True)

projects = load_projects()
init_session()

col1, col2 = st.columns([3, 1])

with col1:
    user_input = st.text_input("🔎 What are you looking for?")
    search_term = user_input.strip().lower()

    all_categories = get_categories(projects)
    selected_category = st.selectbox("📂 Filter by category:", ["All"] + all_categories)

    if user_input:
        extracted_tags = extract_topics_from_text(user_input)
        st.markdown(f"**🎯 Gemini Suggested Tags:** `{', '.join(extracted_tags)}`")
    else:
        extracted_tags = []


    def is_match(proj):
        search_term_lc = search_term.lower()
        proj_tags = [tag.lower() for tag in proj["tags"]]
        proj_title = proj["title"].lower()
        proj_description = proj["description"].lower()
        selected_category_lc = selected_category.lower()

        # ✅ Category match (ignore case)
        category_match = selected_category == "All" or selected_category_lc in proj_tags

        if not search_term:
            return category_match

        # ✅ Direct match (case-insensitive): check if search term is in tags list directly
        direct_tag_match = search_term_lc in proj_tags

        # ✅ Substring tag match
        partial_tag_match = any(search_term_lc in tag for tag in proj_tags)

        # ✅ Fuzzy matching
        fuzzy_match = (
                any(fuzz.partial_ratio(search_term_lc, tag) > 80 for tag in proj_tags) or
                fuzz.partial_ratio(search_term_lc, proj_title) > 80 or
                fuzz.partial_ratio(search_term_lc, proj_description) > 80
        )

        # ✅ LLM tag match (from Gemini)
        extracted_tags_lc = [t.lower() for t in extracted_tags]
        llm_tag_match = any(tag in proj_tags for tag in extracted_tags_lc) if extracted_tags else True

        return category_match and (direct_tag_match or partial_tag_match or fuzzy_match) and llm_tag_match


    filtered_projects = [proj for proj in projects if is_match(proj)]

    if filtered_projects:
        st.markdown("### 🎯 Matching Projects")
        for proj in filtered_projects:
            with st.container():
                fav_key = proj["title"]
                is_fav = fav_key in st.session_state.favorites
                rating = st.session_state.ratings.get(fav_key, 0)

                st.markdown("""<div class='project-card'>""", unsafe_allow_html=True)
                st.image(proj["image"], use_column_width=True)
                st.markdown(f"""
                <div style="
                    background: linear-gradient(90deg, #ffc719, #f72585);
                    border-radius: 10px;
                    padding: 10px 16px;
                    color: #222;
                    font-size: 22px;
                    font-weight: bold;
                    text-align: center;
                    margin-bottom: 10px;
                    border: 1px dashed #ffe863;
                ">
                ~~~ {proj['title']} ~~~
                </div>
                """, unsafe_allow_html=True)
                st.markdown(proj["description"])
                st.markdown(f"[🔗 View Project]({proj['link']})")

                selected = st.selectbox(
                    "⭐ Rate this project:",
                    options=list(rating_emojis.keys()),
                    format_func=lambda x: rating_tooltips[x],
                    index=list(rating_emojis.keys()).index(rating) if rating in rating_emojis else 0,
                    key=f"rating_{fav_key}"
                )
                if selected != rating:
                    st.session_state.ratings[fav_key] = selected
                    upsert_gsheet(fav_key, is_fav, selected)

                button_label = "💔 Remove from Favorites" if is_fav else "❤️ Add to Favorites"
                if st.button(button_label, key=f"favbtn_{fav_key}"):
                    if is_fav:
                        st.session_state.favorites.remove(fav_key)
                    else:
                        st.session_state.favorites.add(fav_key)
                    upsert_gsheet(fav_key, not is_fav, selected)
                    st.rerun()

                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.warning("No matching projects found.")

with col2:
    if st.session_state.favorites:
        st.markdown("### ⭐ Favorites")
        for proj in projects:
            title = proj["title"]
            if title in st.session_state.favorites:
                rating = st.session_state.ratings.get(title, 0)
                if rating == 0:
                    display_title = f"{title} (Please rate it!!!)"
                else:
                    display_title = f"{title} (Rated: {rating}/5)"

                st.markdown(
                    f"<div class='favorite-card'><strong>{display_title}</strong><br>{proj['description'][:80]}...</div>",
                    unsafe_allow_html=True
                )

st.markdown("""
<div class="ai-idea-frame">
    <h2>🤖 Ask AI for Project Ideas</h2>
    <p>Let AI inspire your next data science project. Enter an area of interest and get a custom idea:</p>
""", unsafe_allow_html=True)

project_goal = st.text_input("💡 What area are you interested in developing a project for?")
if st.button("Suggest a Project Idea") and project_goal:
    suggest_prompt = f"Suggest a unique, realistic and creative data science project idea based on this interest: '{project_goal}'. Return only 1 idea with a short title and description."
    response = model.generate_content(suggest_prompt)
    st.success(response.text.strip())

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("""
    <div class='help-box'>
        <h3>🔗 Help & Connect</h3>
        <ul>
            <li><a href='https://github.com/tubakrc' target='_blank'>GitHub</a></li>
            <li><a href='https://www.linkedin.com/in/tubakirca/' target='_blank'>LinkedIn</a></li>
            <li><a href='https://medium.com/@tubakirca' target='_blank'>Medium</a></li>
            <li><a href='mailto:tubakirca@gmail.com'>Email Me</a></li>
        </ul>
        <p style='font-size:1.0em;'>Session ID: {}</p>
    </div>
""".format(st.session_state["user_id"]), unsafe_allow_html=True)
