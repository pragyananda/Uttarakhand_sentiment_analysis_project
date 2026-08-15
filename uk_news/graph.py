"""Knowledge graph: sources, issues and districts as a relation network.

The bubble chart answers "how big is this issue?". The graph answers a
different question — "who is talking about what, and where?" — by making the
relations themselves visible: an edge from Amar Ujala to `recruitment_jobs`
means that publisher covered that issue, weighted by how many times.

Node types are deliberately capped at three. A network is an "all-pairs"
chart form (any two nodes can end up adjacent), which is a stricter colour
test than bars or lines; the validated palette carries exactly three slots
under that test.
"""

from __future__ import annotations

import pandas as pd

# Node type -> categorical slot. Fixed assignment: colour follows the entity,
# never its rank, so filtering never repaints a surviving node type.
NODE_TYPES = {
    "source": {"color": "#2a78d6", "label": "Source"},
    "issue": {"color": "#eb6834", "label": "Issue"},
    "district": {"color": "#1baf7a", "label": "District"},
}


def build_graph(
    df: pd.DataFrame,
    include_districts: bool = True,
    top_sources: int = 12,
    top_issues: int = 10,
    min_edge_weight: int = 1,
    layout_seed: int = 42,
):
    """Return (nodes_df, edges_df, used_df) with 2-D positions ready to plot.

    Nodes carry their own article counts and mean tone; edges carry the number
    of articles that justify the link.

    `used_df` is the frame the graph was actually built from — already cut to
    the top publishers. The click-through panel must filter against THIS, not
    the caller's frame, or a node reporting 32 articles opens a list of 37.
    """
    import networkx as nx

    empty = (pd.DataFrame(), pd.DataFrame(), df.iloc[0:0])
    if df.empty:
        return empty

    from .analysis import explode_by

    work = df.copy()
    work["publisher"] = work["publisher"].fillna("").replace("", None)
    work["publisher"] = work["publisher"].fillna(work["source_name"])

    keep_sources = (work["publisher"].value_counts()
                    .head(top_sources).index.tolist())
    work = work[work["publisher"].isin(keep_sources)]
    if work.empty:
        return empty

    asp = explode_by(work, "aspects")
    if asp.empty:
        return empty
    keep_issues = asp["tag"].value_counts().head(top_issues).index.tolist()
    asp = asp[asp["tag"].isin(keep_issues)]

    G = nx.Graph()

    # --- nodes -----------------------------------------------------------
    def add_nodes(frame, key, ntype):
        agg = frame.groupby(key).agg(
            articles=("id", "nunique"),
            tone=("sentiment_score", "mean")).reset_index()
        for _, r in agg.iterrows():
            G.add_node(f"{ntype}:{r[key]}", name=str(r[key]), ntype=ntype,
                       articles=int(r["articles"]),
                       tone=float(r["tone"]) if pd.notna(r["tone"]) else 0.0)

    add_nodes(work, "publisher", "source")
    add_nodes(asp, "tag", "issue")

    # --- source -> issue edges -------------------------------------------
    se = (asp.groupby(["publisher", "tag"])["id"].nunique()
             .reset_index(name="weight"))
    se = se[se["weight"] >= min_edge_weight]
    for _, r in se.iterrows():
        G.add_edge(f"source:{r['publisher']}", f"issue:{r['tag']}",
                   weight=int(r["weight"]))

    # --- issue -> district edges -----------------------------------------
    if include_districts:
        dis = explode_by(work, "districts")
        if not dis.empty:
            keep_d = dis["tag"].value_counts().head(8).index.tolist()
            dis = dis[dis["tag"].isin(keep_d)]
            add_nodes(dis, "tag", "district")

            # Join issues to districts through the articles they share.
            pair = (asp[["id", "tag"]].rename(columns={"tag": "issue"})
                    .merge(dis[["id", "tag"]].rename(columns={"tag": "district"}),
                           on="id"))
            de = (pair.groupby(["issue", "district"])["id"].nunique()
                      .reset_index(name="weight"))
            de = de[de["weight"] >= max(2, min_edge_weight)]
            for _, r in de.iterrows():
                G.add_edge(f"issue:{r['issue']}", f"district:{r['district']}",
                           weight=int(r["weight"]))

    # Drop orphans — an unconnected dot conveys nothing in a relation graph.
    G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n) == 0])
    if not G.nodes:
        return empty

    # k spreads nodes apart as the graph grows, so labels stay legible.
    pos = nx.spring_layout(G, seed=layout_seed, weight="weight",
                           k=1.9 / max(len(G.nodes) ** 0.5, 1), iterations=220)

    nodes = pd.DataFrame([
        {"node": n, "name": d["name"], "ntype": d["ntype"],
         "articles": d["articles"], "tone": round(d["tone"], 3),
         "degree": G.degree(n),
         "connections": ", ".join(
             sorted(G.nodes[m]["name"] for m in G.neighbors(n))[:6]),
         "x": pos[n][0], "y": pos[n][1]}
        for n, d in G.nodes(data=True)])

    edges = pd.DataFrame([
        {"source": u, "target": v, "weight": d["weight"],
         "x0": pos[u][0], "y0": pos[u][1],
         "x1": pos[v][0], "y1": pos[v][1]}
        for u, v, d in G.edges(data=True)])

    return nodes, edges, work


def articles_for_node(df: pd.DataFrame, node: str) -> pd.DataFrame:
    """Rows behind one graph node, for the click-through panel."""
    if df.empty or not node or ":" not in node:
        return df.iloc[0:0]
    ntype, name = node.split(":", 1)

    if ntype == "source":
        pub = df["publisher"].fillna("").replace("", None).fillna(
            df["source_name"])
        return df[pub == name]
    if ntype == "issue":
        return df[df["aspects_list"].apply(lambda l: name in (l or []))]
    if ntype == "district":
        return df[df["districts_list"].apply(lambda l: name in (l or []))]
    return df.iloc[0:0]
