import dash

from dash import html
from dash import Dash, html, dcc, Input, Output, dcc, html, callback, MATCH, State
import dash_bootstrap_components as dbc
import urllib3

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import dash_bootstrap_components as dbc
from plotly.subplots import make_subplots
import model.queries as qrs
from utils.utils import generate_graphs
from utils.helpers import timer
from flask import request

urllib3.disable_warnings()



dash.register_page(
    __name__,
    path_template="/anomalous_paths/<q>",
    title="ASN-path anomalies",
    description="Visual representation of an ASN-path anomaly",
)

def layout(q=None, **other_unknown_query_strings):
    print(q)
    return html.Div([
        dcc.Location(id='url', refresh=False),
        dcc.Store(id='alarm-data-store'),
        html.Div(id='asn-anomalies-content'),
        html.Div([
            dcc.Loading(id='loading-spinner', type='default', children=[
                html.Div(id='asn-anomalies-graphs')
            ], color='#00245A'),
        ], className="l-h-3 p-2 boxwithshadow page-cont ml-1 p-1")
    ], style={"padding": "0.5% 1.5%"})
    
@callback(
    Output('alarm-data-store', 'data'),
    Input('url', 'pathname')
)
def update_store(pathname):
    if pathname:
        path_parts = pathname.split('/')
        if len(path_parts) > 2 and '=' in path_parts[2]:
            params = path_parts[2].split('&')
            query_params = {param.split('=')[0]: param.split('=')[1] for param in params}
            return query_params
    return {}


@callback(
    Output('asn-anomalies-graphs', 'children'),
    Input('alarm-data-store', 'data')
)
def update_graphs_and_title(query_params):
    if not query_params:
        return html.Div()
        
    alarm_id = query_params.get('id')
    src = query_params.get('src_netsite')
    dest = query_params.get('dest_netsite')
    dt = query_params.get('dt')
    if alarm_id:
        site = query_params.get('site')
        dt = query_params.get('date')
        print("Alarm per site")
        print(site, dt, id)
        alarm = qrs.getAlarm(alarm_id)
        print('URL query:', alarm)
        print("HERE")
        asn_alarms_src = alarm['source']['all_alarm_ids_src']
        asn_alarms_dest = alarm['source']['all_alarm_ids_dest']
        asn_alarms_src_component = asnAnomaliesGroupedAlarmVisualisation(alarm, site, asn_alarms_src, asn_alarms_dest, dt)
        return asn_alarms_src_component
    if src and dest and dt:
        data = qrs.query_ASN_anomalies(src, dest, dt)
        if len(data) == 0:
            return html.Div([
                html.H1(f"No data found for alarm {src} to {dest}"),
                html.P('No data was found for the alarm selected. Please try another alarm.',
                    className="plot-subtitle")
            ], className="l-h-3 p-2 boxwithshadow page-cont ml-1 p-1"), "ASN-path anomalies"

        anomalies = data['anomalies'].values[0]
        title = html.H1(children=html.Div([
            dbc.Row([
                html.Span(f"{src} → {dest}", className="sites-anomalies-title")]),
            dbc.Row([
                html.Span("", style={"margin": "0 10px", "color": "#C50000", "fontSize": "40px"}),
                html.Span(f"Anomalies: {anomalies}", className="anomalies-title", style={"color": "#910000"}),
            ])     
        ], style={"textAlign": "center", "marginBottom": "20px"})
        )

        figures = generate_graphs(data, src, dest, dt)
        return html.Div([
            title,
            figures])
        
    return html.Div('No data available for these parameters.')

@timer
def addNetworkOwners(asn_list):
    asn_list = sorted(asn_list, key=lambda x: int(x) if str(x).isdigit() else float('inf'))
    owners = qrs.getASNInfo(asn_list)
    asn_data = [{"asn": str(asn), "owner": owners.get(str(asn), "Unknown")} for asn in asn_list]
    return asn_data


def generate_asn_cards(asn_data, anomalies):
    # Create a card for each ASN
    print('anomalies')
    print(anomalies)
    print(asn_data)
    cards = [
        dbc.Card(
            dbc.CardBody([
                html.H2(f"AS {asn['asn']}", className="card-title plot-subtitle text-left"),
                html.P(f"{asn['owner']}", className="card-text plot-subtitle text-left"),
            ]),
            className=f"mb-3 shadow-sm h-100 {'border-danger' if int(asn['asn']) in anomalies else 'border-secondary'}",
            style={"width": "100%", "overflow": "hidden", "display": "flex", "flexDirection": "column", "justifyContent": "space-between"}
        )
        for asn in asn_data
    ]

    # Wrap cards in a responsive grid with align-items-stretch
    return dbc.Row([dbc.Col(card, lg=2, md=2, sm=3, className="d-flex") for card in cards], className="g-3 align-items-stretch")


@timer
def generate_graphs(data, src, dest, dt):
    def create_graphs(ipv6_filter):
        heatmap_figure = build_anomaly_heatmap(data[data['ipv6'] == ipv6_filter])
        path_prob_figure = build_position_based_heatmap(src, dest, dt, int(ipv6_filter), data)
        return dbc.Row([
                dbc.Col([
                    dcc.Graph(figure=heatmap_figure, id="asn-sankey-ipv4", className="full-height-graph"),
                    html.P(
                        'This is a sample of the paths between the pair of sites. '
                        'The plot shows new (anomalous) ASNs framed in white. '
                        'The data is based on the alarms of type "ASN path anomalies".',
                        className="plot-subtitle"
                    ),
                ], xxl=6, className="responsive-col"),
                dbc.Col([
                    dcc.Graph(figure=path_prob_figure, id="asn-path-prob-ipv4", className="full-height-graph"),
                    html.P(
                        'The plot shows how often each ASN appears on a position, '
                        'where 1 is 100% of time.',
                        className="plot-subtitle"
                    )
                ], xxl=6, className="responsive-col"),
            ])


    
    # Extract all ASNs and their owners
    asn_list = list(set([asn for sublist in data['repaired_asn_path'] for asn in sublist]))
    asn_owners = addNetworkOwners(asn_list)

    # Create ASN cards
    anomalies = data['anomalies'].explode().unique()
    asn_cards = generate_asn_cards(asn_owners, anomalies)
    # anomalies_cards = generate_asn_anomalies_cards(data)
    if len(data['ipv6'].unique()) == 2:
        figures = html.Div([
            create_graphs(False),  # IPv4
            create_graphs(True),   # IPv6
        ], className="responsive-graphs")
    else:

        heatmap_figure = build_anomaly_heatmap(data)
        path_prob_figure = build_position_based_heatmap(src, dest, dt, -1, data)
        figures = html.Div([
            dbc.Row([
                dbc.Col([
                    dcc.Graph(figure=heatmap_figure, id="asn-sankey-ipv4", className="full-height-graph"),

                    html.P(
                        'This is a sample of the paths between the pair of sites. '
                        'The plot shows new (anomalous) ASNs framed in white. '
                        'The data is based on the alarms of type "ASN path anomalies".',
                        className="plot-subtitle"
                    ),
                ], xxl=6, className="responsive-col"),
                dbc.Col([
                    dcc.Graph(figure=path_prob_figure, id="asn-path-prob-ipv4", className="full-height-graph"),
                    html.P(
                        'The plot shows how often each ASN appears on a position, '
                        'where 1 is 100% of time.',
                        className="plot-subtitle"
                    )
                ], xxl=6, className="responsive-col"),
            ]),

        ], className="responsive-graphs")

    # Return the graphs and the ASN cards
    return html.Div([
        figures,
        html.Div([
            html.H3("Network Owners"),
            asn_cards
        ], className="asn-owner-section")
    ])


@timer
def build_position_based_heatmap(src, dest, dt, ipv, data) -> go.Figure:
    doc = qrs.query_ASN_paths_pos_probs(src, dest, dt, ipv)

    hm = doc["heatmap"]
    ipv = 'IPv6' if doc['ipv6'] else 'IPv4'

    # Create cards with anomalies and probabilities
    anomalious_asns = {}
    for asn in data['anomalies'].explode().unique():
        if asn in hm['asns']:
            probs = hm['probs'][hm['asns'].index(asn)]
            string_info = []
            for i in range(len(probs)):
                if probs[i] > 0:
                    string_info.append(f"pos_{i+1}: {probs[i]:.2%}")
            anomalious_asns[asn] = string_info

    fig = go.Figure()

    # Add the heatmap
    fig.add_trace(go.Heatmap(
        z=hm["probs"],
        x=[f"pos_{p+1}" for p in hm["positions"]],
        y=[str(a) for a in hm["asns"]],
        colorscale=[[0.0, "white"], [0.001, "#caf0f8"], [0.4, "#00b4d8"], [0.9, "#03045e"], [1, "black"]],
        zmin=0, zmax=1,
        xgap=0.8, ygap=0.8,
        hovertemplate="ASN %{y}<br>Position %{x}<br>Frequency: %{z:.2%}<extra></extra>"
    ))

    # positions of anomalies to mark
    x_labels = [f"pos_{p+1}" for p in hm["positions"]]

    # get positions of anomalous cells and mark them with values
    for asn in anomalious_asns:
        if asn in hm["asns"]:
            row = hm["asns"].index(asn)
            for col, val in enumerate(hm["probs"][row]):
                if val > 0:
                    fig.add_trace(go.Scatter(
                        x=[x_labels[col]],
                        y=[str(asn)],
                        mode="text",
                        text=[str("{:.2%}".format(val))],
                        textfont=dict(color="#C50000", size=12, family="Arial Black"),
                        hoverinfo='skip',
                        showlegend=False
                    ))


    fig.update_layout(
        title=(f"{ipv} paths - position-based ASN frequency (7 days stats)"),
        xaxis_title="Position on Path",
        yaxis_title="ASN",
        height=600
    )

    return fig

@timer
def build_anomaly_heatmap(subset_sample):
    columns = ['src_netsite', 'dest_netsite', 'anomalies', 'ipv6']
    src_site, dest_site, anomaly, ipv = subset_sample[columns].values[0]
    ipv = 'IPv6' if ipv else 'IPv4'

    subset_sample['last_appearance_path'] = pd.to_datetime(subset_sample['last_appearance_path'], errors='coerce')
    time_start = subset_sample['last_appearance_path'].min()
    time_end = subset_sample['last_appearance_path'].max()
    subset_sample['last_appearance_short'] = subset_sample['last_appearance_path'].dt.strftime('%H:%M:%S %d-%b')

    print('Size of dataset:', len(subset_sample))
    max_length = subset_sample["path_len"].max()

    pivot_df = pd.DataFrame(
        subset_sample['repaired_asn_path'].tolist(),
        index=subset_sample.index,
        columns=[f"pos_{i+1}" for i in range(max_length)]
    ).map(lambda x: int(x) if isinstance(x, (int, float)) and not pd.isna(x) else x)

    font_size = 15
    if max_length > 24: font_size = 10
    elif max_length > 18: font_size = 11
    elif max_length > 16: font_size = 13

    # map unique ASNs to colors
    unique_rids = pd.Series(pivot_df.stack().unique()).dropna().tolist()

    # normal path (first row)
    doc = qrs.query_ASN_paths_pos_probs(src_site, dest_site, subset_sample['last_appearance_path'].min(), ipv == 'IPv6')
    hm = doc["heatmap"]
    
    
    asns = [str(a) for a in hm["asns"]]
    probs = np.array(hm["probs"])
    # normal path is considered to be the one that appears in 90% of cases
    max_indices = probs[:, probs.sum(axis=0) > 0.899999].argmax(axis=0)
    best_asns = [int(asns[i]) for i in max_indices] 
    # setting up colors
    unique_rids += [int(x) for x in best_asns if int(x) not in unique_rids]
    if 0 not in unique_rids:
        unique_rids.append(0)
    rid_to_index = {rid: i + 1 for i, rid in enumerate(unique_rids)}
    rid_to_index[np.nan] = 0
    base_colors = px.colors.qualitative.Prism + px.colors.qualitative.Bold
    expanded_colors = (base_colors * (len(unique_rids) // len(base_colors) + 1))[:len(unique_rids)]
    color_list = ["#FFFFFF"] + expanded_colors
    color_list[rid_to_index[0]] = '#000000'
    for asn in anomaly:
        color_list[rid_to_index[asn]] = "#C50000"
    color_list[rid_to_index[0]] = '#000000'
    index_to_color = {i: color_list[i] for i in range(len(color_list))}
    index_df = pivot_df.map(lambda x: rid_to_index.get(x, 0))
    best_asns_colors = [rid_to_index.get(asn, 0) for asn in best_asns]

    
    
    best_asns_str = [str(asn) for asn in best_asns]
    positions = hm["positions"]
    # calculate length of graph
    maxLength = max(len(max_indices), index_df.columns.size)
    
    hover_bgcolor = np.array([index_to_color.get(z, '#FFFFFF') for row in index_df.values for z in row]).reshape(index_df.shape)
    customdata = pivot_df.map(lambda x: str(int(x)) if pd.notna(x) else "").values


    usual_heatmap_trace = go.Heatmap(
        z=[best_asns_colors],
        x=[f"pos_{p+1}" for p in range(maxLength)],
        y=["Most Probable Path"],
        colorscale=color_list,
        zmin=0,
        zmax=len(unique_rids),
        xgap=0.5,
        ygap=0.5,
        customdata=[best_asns_str],
        hoverlabel=dict(bgcolor=hover_bgcolor),
        hovertemplate="<b>Position: %{x}</b><br><b>ASN: %{customdata}</b><extra></extra>",
        showscale=False
    )

    # paths with anomaly (second row)
    heatmap_trace = go.Heatmap(
        z=index_df.values,
        x=index_df.columns,
        y=subset_sample['last_appearance_short'],
        colorscale=color_list,
        zmin=0,
        zmax=len(unique_rids),
        xgap=0.5,
        ygap=0.5,
        customdata=customdata,
        hoverlabel=dict(bgcolor=hover_bgcolor),
        hovertemplate="<b>Position: %{x}</b><br><b>ASN: %{customdata}</b><extra></extra>",
        showscale=False
    )

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        row_heights=[0.1, 0.9],
        subplot_titles=[
            "Regular Path (Based on 7-day frequency observation)",
            f"Sample of Regular vs Anomalious Paths from {time_start.strftime('%H:%M:%S %d-%b')} to {time_end.strftime('%H:%M:%S %d-%b')}"
        ]
    )
    fig.add_trace(usual_heatmap_trace, row=1, col=1)
    fig.add_trace(heatmap_trace, row=2, col=1)

    
    for col_idx, asn in enumerate(best_asns_str):
        fig.add_annotation(
            x=f"pos_{positions[col_idx]+1}",
            y="Most Probable Path",
            text=asn,
            showarrow=False,
            font=dict(color='white', size=font_size, family="Arial"),
            row=1, col=1
        )
                    
    for idx, row in enumerate(pivot_df.values):
        for col_idx, asn in enumerate(row):
            if ~np.isnan(asn):
                if asn in anomaly:
                    fig.add_annotation(
                        x=index_df.columns[col_idx],
                        y=subset_sample['last_appearance_short'].iloc[idx],
                        text=int(asn),
                        showarrow=False,
                        bordercolor='white',
                        font=dict(color='white', size=font_size, family="Arial"),
                        row=2, col=1
                    )
                else:
                    fig.add_annotation(
                        x=index_df.columns[col_idx],
                        y=subset_sample['last_appearance_short'].iloc[idx],
                        text=int(asn),
                        showarrow=False,
                        font=dict(color='white', size=font_size, family="Arial"),
                        row=2, col=1
                    )

    fig.update_layout(
        title_text=f"{ipv} ASN Paths — Regular vs Anomaly Period",
        height=700,
        margin=dict(r=150),
        paper_bgcolor='#FFFFFF',
        plot_bgcolor='#FFFFFF',
        yaxis2=dict(autorange='reversed', type='category', fixedrange=False),
        yaxis1=dict(showticklabels=False)
    )
    return fig

@dash.callback(
    [
      Output({'type': 'asn-collapse', 'index': MATCH},  "is_open"),
      Output({'type': 'asn-collapse', 'index': MATCH},  "children")
    ],
    [
      Input({'type': 'asn-collapse-button', 'index': MATCH}, "n_clicks"),
      Input({'type': 'asn-collapse-button', 'index': MATCH}, "value"),
      Input('asn-alarm-store', 'data')
    ],
    [State({'type': 'asn-collapse', 'index': MATCH},  "is_open")],
)
def toggle_collapse(n, alarmData, alarm, is_open):
    ctx = dash.callback_context
    if ctx.triggered:
        if n:
            if is_open==False:
                source = alarmData['src']
                destination = alarmData['dest']
                date = alarmData['date']
                data = qrs.query_ASN_anomalies(source, destination, date)
                visuals = generate_graphs(data, source, destination, date)
                return [not is_open, visuals]
            else:
                return [not is_open, None]
        return [is_open, None]
    return dash.no_update

@timer
def asnAnomaliesGroupedAlarmVisualisation(alarm, site, sites_list_src, sites_list_dest, date):
    alarms_dest = []
    alarms_src = []
    if len(sites_list_src) > 0:
        alarms_src = [[src[0]+' to '+site, src[0], site, 'dest'] for src in sites_list_src]
    if len(sites_list_dest) > 0:
        alarms_dest = [[site+' to '+dest[0], site, dest[0], 'src'] for dest in sites_list_dest]
    all_alarms = alarms_dest + alarms_src
    return_component = html.Div([
            dbc.Row([
              dbc.Row([
                dbc.Col([
                  html.H3("ASN path anomalies", className="text-center bold p-3"),
                  html.H5(date, className="text-center bold"),
                ], lg=2, md=12, className="p-3"),
                dbc.Col(
                    html.Div([
                        dbc.Row([
                            dbc.Row([
                                html.H1(f"Summary for {site}", className="text-left"),
                                html.Hr(className="my-2")
                            ]),
                            dbc.Row([
                                html.P([
                                    f"{alarm['source']['total_paths_anomalies']} path change(s) were detected involving site {site}. "
                                    f"New ASN(s) appeared on routes where {site} acted as a source {len(alarm['source']['as_source_to'])} time(s) "
                                    f"and {len(alarm['source']['as_destination_from'])} time(s) as destination. "
                                    "You can see visualisation for all the path anomalies below or explore paths for a given site and date here: ",
                                    html.A("Explore paths", href=f"{request.host_url}/explore-paths", target="_blank")
                                ], className='subtitle')
                            ], justify="start"),
                        ])
                    ]),
                    lg=10, md=12, className="p-3"
                )
              ], className="boxwithshadow alarm-header pair-details g-0", justify="between", align="center")                
            ], style={"padding": "0.5% 1.5%"}, className='g-0'),
          dcc.Store(id='asn-alarm-store', data=alarm),
          dbc.Row([
            html.Div(id=f'site-section-asn-anomalies-{a[0]}',
              children=[
                dbc.Button(
                    a[0],
                    value = {'src': a[1], 'dest': a[2], 'date': date},
                    id={
                        'type': 'asn-collapse-button',
                        'index': f'asn-anomalies'+a[0]
                    },
                    className="collapse-button",
                    color="white",
                    n_clicks=0,
                ),
                dcc.Loading(
                  dbc.Collapse(
                      id={
                          'type': 'asn-collapse',
                          'index': f'asn-anomalies'+a[0]
                      },
                      is_open=False, className="collaps-container rounded-border-1"
                ), color='#e9e9e9', style={"top":0}),
              ]) for a in all_alarms
            ], className="rounded-border-1 g-0", align="start", style={"padding": "0.5% 1.5%"})
          ])
    return return_component