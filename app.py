import os
import json
import urllib.parse

import pandas as pd
import dash
from dash import html, dcc, dash_table
from dash.dependencies import Input, Output, State
import dash_leaflet as dl
import dash_bootstrap_components as dbc

# ──────────────────────────────────────────────────────────────────────────────
# 1. LOAD & PREPARE DATA
# ──────────────────────────────────────────────────────────────────────────────
DATA_PATH  = "stakeholders.csv"
CACHE_PATH = "geocoded_cache.json"

df = pd.read_csv(DATA_PATH, encoding="latin-1")
df["RawStatus"] = df["Status"].astype(str)

def normalize_status(x):
    x = x.lower()
    if   "keynote"    in x: return "Keynote speaker"
    elif "general"    in x and "participant" in x:
                             return "General Participant"
    elif "declined"   in x: return "Declined"
    elif "organising" in x: return "Organising Committee"
    elif "session"    in x or "oral" in x:
                             return "Session presentation"
    elif "panel"      in x: return "Panel discussion"
    elif "sponsor"    in x: return "Sponsor"
    elif x.strip() in ["tbc","to be confirmed"]:
                             return "Invited to attend Symposium"
    else:                  return "Stakeholder"

status_levels = [
    "Keynote speaker",
    "General Participant",
    "Declined",
    "Organising Committee",
    "Session presentation",
    "Panel discussion",
    "Sponsor",
    "Invited to attend Symposium",
    "Stakeholder"
]

df["Status"] = df["RawStatus"].apply(normalize_status)
df["Status"] = pd.Categorical(df["Status"],
                              categories=status_levels,
                              ordered=True)

# drop rows without a country
df = df[df["Country"].notna() & (df["Country"]!="")].copy()

# build Location key
df["Location"] = df.apply(
    lambda r: f"{r['City']}, {r['Country']}"
              if pd.notna(r["City"]) and r["City"]!="" else r["Country"],
    axis=1
)

# load or init geocode cache
if os.path.exists(CACHE_PATH):
    with open(CACHE_PATH) as f:
        cache = json.load(f)
else:
    cache = {}

# inject cached coords
df["Latitude"]  = df["Location"].map(lambda loc: cache.get(loc,(None,None))[0])
df["Longitude"] = df["Location"].map(lambda loc: cache.get(loc,(None,None))[1])

# drop any still‐missing
df = df.dropna(subset=["Latitude","Longitude"])

# unique filter values
category_levels    = sorted(df["Category"].dropna().unique())
country_levels     = sorted(df["Country"].dropna().unique())
affiliation_levels = sorted(df["Affiliation"].dropna().unique())

# ──────────────────────────────────────────────────────────────────────────────
# 2. COLOUR PALETTE
# ──────────────────────────────────────────────────────────────────────────────
status_to_colour = {
    "Keynote speaker":            "#2ecc71",
    "General Participant":        "#ffffb3",
    "Declined":                   "#e74c3c",
    "Organising Committee":       "#3498db",
    "Session presentation":       "#f1c40f",
    "Panel discussion":           "#9b59b6",
    "Sponsor":                    "#d4ac0d",
    "Invited to attend Symposium":"#f39c12",
    "Stakeholder":                "#808080"
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. BASEMAP URL
# ──────────────────────────────────────────────────────────────────────────────
LIGHT_BASEMAP = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"

# ──────────────────────────────────────────────────────────────────────────────
# 4. DASH SETUP
# ──────────────────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True
)
app.title = "Extrusion Stakeholder Map"

# ──────────────────────────────────────────────────────────────────────────────
# 5. LAYOUT
# ──────────────────────────────────────────────────────────────────────────────
app.layout = dbc.Container(fluid=True, children=[

    
    # Page title
    dbc.Row([
        dbc.Col(html.H1(
            "Food & Feed Extrusion – Global Stakeholder Network",
            className="text-center",
            style={"fontSize":"2.5rem","fontWeight":"300"}
        ), width=12)
    ], className="my-4"),
    
    # Top banner with image & status‐pills
    html.Div(
        html.Div([
            html.Img(
                src=app.get_asset_url("banner.png"),
                style={"height":"270px","marginRight":"1rem"}  # 1.5× taller
            ),
            html.Div([
                html.H5(
                  "International Symposium on Food & Feed Extrusion",
                  style={"color":"#fff","marginBottom":".25rem"}
                ),
                html.P(
                  "Filter the map by Symposium attendance status:",
                  className="fw-bold",
                  style={"color":"#fff","marginBottom":".5rem"}
                ),
                dbc.Checklist(
                  id="status_select",
                  options=[{"label":s,"value":s} for s in status_levels],
                  value=[],            # empty = show all
                  inline=True,
                  inputClassName="btn-check",
                  labelClassName=(
                    "btn btn-outline-light btn-lg "
                    "rounded-pill me-2 mb-2"
                  )
                )
            ], style={"display":"flex","flexDirection":"column"})
        ], style={"display":"flex","alignItems":"center"}),
        style={
            "backgroundColor":"#0096D6",
            "padding":"1rem",
            "borderRadius":"0.5rem",
            "boxShadow":"0 2px 4px rgba(0,0,0,0.1)",
            "marginBottom":"1.5rem"
        }
    ),

    # Tabs
    dcc.Tabs(id="tabs", value="explore", children=[
        dcc.Tab(label="Explore Map", value="explore"),
        dcc.Tab(label="Submit Stakeholder", value="submit")
    ]),

    html.Div(id="tab-content", className="mt-4")

], style={"font-family":"Arial, sans-serif"})

# ──────────────────────────────────────────────────────────────────────────────
# 6. RENDER TABS
# ──────────────────────────────────────────────────────────────────────────────
@app.callback(Output("tab-content","children"),
              Input("tabs","value"))
def render_tab(tab):
    if tab == "explore":
        # ─── sidebar filters ─────────────────────────────────────────────
        filters = dbc.Col(width=3, className="pe-4", children=[

            dbc.Label("Search all", className="fw-bold"),
            dcc.Input(id="global_search",
                      placeholder="Type to search…",
                      type="text", debounce=True,
                      className="form-control mb-3"),

            dbc.Label("Category", className="fw-bold"),
            dbc.Checklist(
                id="category_select",
                options=[{"label":c,"value":c} for c in category_levels],
                value=[], inline=True,
                inputClassName="btn-check",
                labelClassName="btn btn-outline-primary me-1 mb-1"
            ),
            html.Br(),

            dbc.Label("Country", className="fw-bold mt-3"),
            dcc.Dropdown(
                id="country_select",
                options=[{"label":c,"value":c} for c in country_levels],
                value=[], multi=True,
                placeholder="All countries"
            ),
            html.Br(),

            dbc.Label("Affiliation", className="fw-bold"),
            dcc.Dropdown(
                id="affiliation_select",
                options=[{"label":a,"value":a} for a in affiliation_levels],
                value=[], multi=True,
                placeholder="All affiliations"
            ),

            html.Br(),
            dbc.Button("Reset filters", id="reset-filters",
                       color="secondary", outline=True,
                       className="mb-3 w-100"),

        ])

        # ─── map + legend + table ────────────────────────────────────────
        map_area = dbc.Col(width=9, children=[
            html.Div(id="legend", className="d-flex mb-2"),

            dl.Map(
                id="map", center=[20,0], zoom=1, children=[],
                style={
                    "width":"100%","height":"60vh",
                    "borderRadius":"4px",
                    "boxShadow":"2px 2px 5px rgba(0,0,0,0.1)"
                }
            ),

            html.H5("Visible stakeholders", className="mt-3"),
            dash_table.DataTable(
                id="visible_table",
                columns=[{"name":c,"id":c}
                         for c in ["Name","Position","Affiliation",
                                   "Country","Category","Status"]],
                page_size=10,
                style_table={"overflowX":"auto"},
                style_header={"backgroundColor":"#f8f9fa","fontWeight":"bold"}
            )
        ])

        return dbc.Row([filters, map_area], className="g-0")

    # ──────────────────────────────────────────────────────────────────────────
    # Submit‐stakeholder tab
    # ──────────────────────────────────────────────────────────────────────────
    return dbc.Card(
        body=True, className="mx-auto", style={"maxWidth":"600px"},
        children=[
            html.H3("Submit New Stakeholder", className="text-center mb-4"),
            dbc.Form([
                dbc.Label("Name"), dbc.Input(id="sub-name", type="text"),
                html.Br(),
                dbc.Label("Department / Program"),
                dbc.Input(id="sub-department", type="text"),
                html.Br(),
                dbc.Label("Position"), dbc.Input(id="sub-position", type="text"),
                html.Br(),
                dbc.Label("Country"), dbc.Input(id="sub-country", type="text"),
                html.Br(),
                dbc.Label("City"),    dbc.Input(id="sub-city",    type="text"),
                html.Br(),
                dbc.Label("Status"),
                dcc.Dropdown(
                    id="sub-status",
                    options=[{"label":s,"value":s} for s in status_levels],
                    value="Stakeholder", clearable=False
                ),
                html.Br(),
                dbc.Button("Prepare Email", id="submit-button",
                           color="primary", className="w-100"),
                html.Div(id="submit-output", className="mt-3")
            ])
        ]
    )

# ──────────────────────────────────────────────────────────────────────────────
# 7. RESET FILTERS
# ──────────────────────────────────────────────────────────────────────────────
@app.callback(
    Output("status_select","value"),
    Output("category_select","value"),
    Output("country_select","value"),
    Output("affiliation_select","value"),
    Output("global_search","value"),
    Input("reset-filters","n_clicks"),
    prevent_initial_call=True
)
def reset_filters(_):
    return [], [], [], [], ""

# ──────────────────────────────────────────────────────────────────────────────
# 8. UPDATE MAP & LEGEND
# ──────────────────────────────────────────────────────────────────────────────
@app.callback(
    Output("map","children"),
    Output("map","center"),
    Output("legend","children"),
    Input("status_select","value"),
    Input("category_select","value"),
    Input("country_select","value"),
    Input("affiliation_select","value"),
    Input("global_search","value")
)
def update_map(statuses, cats, countries, affils, search):
    # 1) FILTER
    m = pd.Series(True, index=df.index)
    if statuses:  m &= df["Status"].isin(statuses)
    if cats:      m &= df["Category"].isin(cats)
    if countries: m &= df["Country"].isin(countries)
    if affils:    m &= df["Affiliation"].isin(affils)
    if search:
        s = search.strip()
        txt = df[["Name","Affiliation","Category",
                  "Country","City","Position"]]\
              .apply(lambda c: c.astype(str)
                                .str.contains(s, case=False, na=False)
                     ).any(axis=1)
        m &= txt
    dff = df[m]

    # 2) LEGEND: if user clicked pills, show those, else show all
    present = statuses if statuses else status_levels
    legend_items = [
        html.Div([
            html.Span(style={
                "display":"inline-block","width":"16px","height":"16px",
                "backgroundColor": status_to_colour[s],
                "marginRight":"8px","border":"1px solid #555"
            }),
            html.Span(s)
        ], className="me-3")
        for s in present
    ]

    # 3) Base tile (always light)
    tile = dl.TileLayer(
        url=LIGHT_BASEMAP,
        attribution="&copy; CartoDB, ESRI, Stamen"
    )

    # 4) One CircleMarker per unique (lat,lon)
    markers = []
    for (lat, lon), group in dff.groupby(["Latitude","Longitude"]):
        cnt  = len(group)
        row0 = group.iloc[0]
        col  = status_to_colour[row0.Status]
        radius = 8 + 2*min(cnt,10)

        # Tooltip & Popup
        if cnt == 1:
            tip   = row0.Name
            popup = dl.Popup(html.Div([
                html.Strong(row0.Name), html.Br(),
                row0.Position, html.Br(),
                row0.Affiliation, html.Br(),
                f"{row0.City}, {row0.Country}"
            ]))
        else:
            tip   = f"{cnt} people"
            popup = dl.Popup(html.Div([
                html.H5(f"{cnt} people here", style={"marginBottom":".5rem"}),
                html.Ul([
                    html.Li(f"{r.Name} ({r.Status})")
                    for _,r in group.iterrows()
                ], style={"paddingLeft":"1rem","margin":0})
            ], style={"maxHeight":"200px","overflowY":"auto"}))

        markers.append(
            dl.CircleMarker(
                id=f"marker-{lat:.5f}-{lon:.5f}",
                center=[lat,lon],
                radius=radius,
                color=col,
                fillColor=col,
                fillOpacity=0.8,
                weight=1,
                children=[ dl.Tooltip(tip), popup ]
            )
        )

    return [tile] + markers, [20,0], legend_items

# ──────────────────────────────────────────────────────────────────────────────
# 9. VISIBLE‐STAKEHOLDERS TABLE
# ──────────────────────────────────────────────────────────────────────────────
@app.callback(
    Output("visible_table","data"),
    Input("map","bounds"),
    Input("status_select","value"),
    Input("category_select","value"),
    Input("country_select","value"),
    Input("affiliation_select","value"),
    Input("global_search","value")
)
def update_visible_table(bounds, statuses, cats, countries,
                         affils, search):

    m = pd.Series(True, index=df.index)
    if statuses:  m &= df["Status"].isin(statuses)
    if cats:      m &= df["Category"].isin(cats)
    if countries: m &= df["Country"].isin(countries)
    if affils:    m &= df["Affiliation"].isin(affils)
    if search:
        s = search.strip()
        txt = df[["Name","Affiliation","Category",
                  "Country","City","Position"]]\
              .apply(lambda c: c.astype(str)
                                .str.contains(s, case=False, na=False)
                     ).any(axis=1)
        m &= txt

    vis = df[m]
    if bounds:
        sw, ne = bounds
        vis = vis[
            vis["Latitude"].between(sw[0], ne[0]) &
            vis["Longitude"].between(sw[1], ne[1])
        ]

    return vis[["Name","Position","Affiliation",
                "Country","Category","Status"]].to_dict("records")

# ──────────────────────────────────────────────────────────────────────────────
# 10. SUBMISSION EMAIL
# ──────────────────────────────────────────────────────────────────────────────
@app.callback(
    Output("submit-output","children"),
    Input("submit-button","n_clicks"),
    State("sub-name","value"),
    State("sub-department","value"),
    State("sub-position","value"),
    State("sub-country","value"),
    State("sub-city","value"),
    State("sub-status","value"),
    prevent_initial_call=True
)
def prepare_email(n, name, dept, pos, country, city, status):
    fields = {
        "Name": name,
        "Department/Program": dept,
        "Position": pos,
        "Country": country,
        "City": city,
        "Status": status
    }
    body = "\n".join(f"{k}: {v}" for k,v in fields.items())
    mailto = (
        "mailto:jordan.pennells@csiro.au"
        "?subject=" + urllib.parse.quote("New Extrusion Symposium Stakeholder") +
        "&body="    + urllib.parse.quote(body)
    )
    return dbc.Alert(
        html.A("✉ Click to send your submission",
               href=mailto, target="_blank"),
        color="success"
    )

# ──────────────────────────────────────────────────────────────────────────────
# 11. RUN
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
