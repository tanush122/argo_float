import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px

DB_PATH = "data/floats.db"

@st.cache_data
def get_summary():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT float_id, COUNT(*) AS n FROM measurements GROUP BY float_id",
        conn
    )
    conn.close()
    return df

@st.cache_data
def get_profiles(float_id, max_rows=5000):
    conn = sqlite3.connect(DB_PATH)
    q = """
        SELECT profile_date, depth, temperature, salinity, mld
        FROM measurements
        WHERE float_id=?
        ORDER BY profile_date, depth
        LIMIT ?
    """
    df = pd.read_sql_query(q, conn, params=(float_id, max_rows))
    conn.close()
    return df

st.title("ARGO Float Explorer")

# Float summary table
summary = get_summary()
st.subheader("Loaded floats")
st.dataframe(summary)

float_ids = summary["float_id"].dropna().astype(str).tolist()
if float_ids:
    chosen = st.selectbox("Select float", float_ids)
    data = get_profiles(chosen)
    st.subheader(f"Profiles for {chosen}")

    if not data.empty:
        # Profile picker
        prof_dates = sorted(data["profile_date"].dropna().unique().tolist())
        sel = st.selectbox("Profile date", prof_dates)
        prof = data[data["profile_date"] == sel].sort_values("depth")

        # Temperature plot
        fig_t = px.line(
            prof, x="temperature", y="depth",
            title=f"Temperature vs Depth ({sel})"
        )
        fig_t.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_t, use_container_width=True)

        # Salinity plot
        fig_s = px.line(
            prof, x="salinity", y="depth",
            title=f"Salinity vs Depth ({sel})"
        )
        fig_s.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_s, use_container_width=True)

        # Mixed layer depth note
        if prof["mld"].notna().any():
            mld_val = prof["mld"].dropna().iloc[0]
            st.info(f"Estimated mixed layer depth: {mld_val:.1f} m")
    else:
        st.warning("No data for selected float.")

    # --- Chat Q&A ---
    st.markdown("---")
    st.subheader("Chat with ARGO Data")
    query = st.text_input(
        "Ask a question (try: How many profiles? Latest profile? Max temperature?)"
    )

    if query:
        conn = sqlite3.connect(DB_PATH)
        q_lower = query.strip().lower()

        def reply(text):
            st.markdown(f"**Bot:** {text}")

        # 1) Count profiles
        if "how many profiles" in q_lower or "count profiles" in q_lower:
            df_q = pd.read_sql_query(
                """
                SELECT COUNT(DISTINCT profile_date) AS profiles
                FROM measurements
                WHERE float_id=?
                """,
                conn, params=(chosen,)
            )
            n = int(df_q["profiles"].iloc[0])
            reply(f"This float has {n} profiles.")

        # 2) Latest profile
        elif "latest profile" in q_lower or "last profile" in q_lower:
            df_q = pd.read_sql_query(
                """
                SELECT profile_date
                FROM measurements
                WHERE float_id=?
                  AND profile_date IS NOT NULL
                GROUP BY profile_date
                ORDER BY profile_date DESC
                LIMIT 1
                """,
                conn, params=(chosen,)
            )
            if not df_q.empty:
                reply(f"The most recent profile date is {df_q['profile_date'].iloc[0]}.")
            else:
                reply("No profile dates found.")

        # 3) Max temperature
        elif "max temperature" in q_lower or "highest temperature" in q_lower:
            df_q = pd.read_sql_query(
                """
                SELECT profile_date, MAX(temperature) AS max_temp
                FROM measurements
                WHERE float_id=?
                GROUP BY profile_date
                ORDER BY max_temp DESC
                LIMIT 5
                """,
                conn, params=(chosen,)
            )
            reply("Top 5 profiles by peak temperature:")
            st.table(df_q)

        # 4) Min salinity
        elif "min salinity" in q_lower or "lowest salinity" in q_lower:
            df_q = pd.read_sql_query(
                """
                SELECT profile_date, MIN(salinity) AS min_sal
                FROM measurements
                WHERE float_id=?
                GROUP BY profile_date
                ORDER BY min_sal ASC
                LIMIT 5
                """,
                conn, params=(chosen,)
            )
            reply("Top 5 freshest profiles (lowest salinity):")
            st.table(df_q)

        # 5) MLD summary
        elif "mld" in q_lower or "mixed layer" in q_lower:
            df_q = pd.read_sql_query(
                """
                SELECT profile_date,
                       ROUND(AVG(mld),1) AS avg_mld,
                       ROUND(MIN(mld),1) AS min_mld,
                       ROUND(MAX(mld),1) AS max_mld
                FROM measurements
                WHERE float_id=?
                GROUP BY profile_date
                ORDER BY profile_date DESC
                LIMIT 10
                """,
                conn, params=(chosen,)
            )
            reply("Recent mixed layer depth statistics:")
            st.table(df_q)

        # 6) Where condition (e.g., where salinity > 36.5)
        elif "where" in q_lower and (">" in q_lower or "<" in q_lower):
            import re
            m = re.search(r"(temperature|salinity)\s*([<>]=?)\s*([0-9]+\.?[0-9]*)", q_lower)
            if m:
                col, op, val = m.groups()
                sql = f"""
                    SELECT profile_date, depth, {col}
                    FROM measurements
                    WHERE float_id=?
                      AND {col} {op} ?
                    ORDER BY profile_date, depth
                    LIMIT 500
                """
                df_q = pd.read_sql_query(sql, conn, params=(chosen, float(val)))
                reply(f"Showing rows where {col} {op} {val}:")
                st.dataframe(df_q)
            else:
                reply("Please use a format like: `where salinity > 36.5`.")

        else:
            reply("Sorry, I don't understand. Try: "
                  "`How many profiles?`, `Latest profile?`, `Max temperature`, "
                  "`Min salinity`, `MLD summary`, `Where salinity > 36.5`.")

        conn.close()

else:
    st.warning("No floats found in database.")
