import numpy as np
import dash
from dash import Dash, dash_table, dcc, html
import dash_bootstrap_components as dbc
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State

import plotly.graph_objects as go
import plotly.express as px

import pandas as pd
from flask import request
from datetime import date, timedelta, datetime
from time import time

from model.Alarms import Alarms
import utils.helpers as hp
from utils.helpers import timer
import model.queries as qrs
from utils.parquet import Parquet
import pycountry
import os
# import psconfig.api


@timer
def builMap(mapDf):
    # usually test and production sites are at the same location,
    # so we add some noise to the coordinates to make them visible
    mapDf['lat'] = mapDf['lat'].astype(float) + np.random.normal(scale=0.01, size=len(mapDf))
    mapDf['lon'] = mapDf['lon'].astype(float) + np.random.normal(scale=0.01, size=len(mapDf))

    color_mapping = {
    '⚪': '#6a6969',
    '🔴': '#c21515',
    '🟡': '#ffd500',
    '🟢': '#01a301'
    }

    size_mapping = {
    '⚪': 4,
    '🔴': 3,
    '🟡': 2,
    '🟢': 1
    }

    mapDf['size'] = mapDf['Status'].map(size_mapping)

    fig = px.scatter_mapbox(data_frame=mapDf, lat="lat", lon="lon",
                        color="Status",
                        color_discrete_map=color_mapping,
                        size_max=11,
                        size='size',
                        hover_name="site",
                        custom_data=['Infrastructure','Network','Other'],
                        zoom=1,
                    )

    fig.update_traces(
        hovertemplate="<br>".join([
            "<b>%{hovertext}</b>",
            "Infrastructure: %{customdata[0]}",
            "Network: %{customdata[1]}",
            "Other: %{customdata[2]}",
        ]),
        marker=dict(opacity=0.7)
    )

    fig.update_layout(
        margin=dict(t=0, b=0, l=0, r=0),
        mapbox=dict(
            accesstoken='pk.eyJ1IjoicGV0eWF2IiwiYSI6ImNraDNwb3k2MDAxNnIyeW85MTMwYTU1eWoifQ.1QQ1E5mPh3hoZjK5X5LH7Q',
            bearing=0,
            center=go.layout.mapbox.Center(
                lat=43,
                lon=-6
            ),
            pitch=0,
            style='mapbox://styles/petyav/ckh3spvk002i419mzf8m9ixzi'
        ),
        showlegend=False,
        title = 'Status of all sites in the past 48 hours',
        template='plotly_white'
    )

    return fig


@timer
def generate_status_table(alarmCnt):
    # remove the path changed between sites event because sites tend to show big numbers for this event
    # and it dominates the table. Use the summary event "path changed" instead
    alarmCnt = alarmCnt[alarmCnt['event'] != 'path changed between sites']

    red_sites = alarmCnt[(alarmCnt['event']=='bandwidth decreased from/to multiple sites')
            & (alarmCnt['cnt']>0)]['site'].unique().tolist()

    yellow_sites = alarmCnt[(alarmCnt['event'].isin(['path changed', 'ASN path anomalies']))
                    & (alarmCnt['cnt']>0)]['site'].unique().tolist()

    grey_sites = alarmCnt[(alarmCnt['event'].isin(['firewall issue', 'source cannot reach any', 'complete packet loss']))
                    & (alarmCnt['cnt']>0)]['site'].unique().tolist()

    catdf = qrs.getSubcategories()
    catdf = pd.merge(alarmCnt, catdf, on='event', how='left')

    df = catdf.groupby(['site', 'category'])['cnt'].sum().reset_index()

    df_pivot = df.pivot(index='site', columns='category', values='cnt')
    df_pivot.reset_index(inplace=True)

    df_pivot.sort_values(by=['Network', 'Infrastructure', 'Other'], ascending=False, inplace=True)


    def give_status(site):
        if site in red_sites:
            return '🔴'

        elif site in yellow_sites:
            return '🟡'
        
        elif site in grey_sites:
            return '⚪'
        return '🟢'

    df_pivot['Status'] = df_pivot['site'].apply(give_status)
    df_pivot['site name'] = df_pivot.apply(lambda row: f"{row['Status']} {row['site']}", axis=1)

    df_pivot = df_pivot[['site', 'site name', 'Status', 'Network', 'Infrastructure', 'Other']]

    url = f'{request.host_url}site'
    df_pivot['url'] = df_pivot['site'].apply(lambda name: 
                                             f"<a class='btn btn-secondary' role='button' href='{url}/{name}' target='_blank'>See latest alarms</a>" if name else '-')

    status_order = ['🔴', '🟡', '🟢', '⚪']
    df_pivot = df_pivot.sort_values(by='Status', key=lambda x: x.map({status: i for i, status in enumerate(status_order)}))
    display_columns = [col for col in df_pivot.columns.tolist() if col not in ['Status', 'site']]
    # print(display_columns)
    # print(df_pivot)
    # print(df_pivot.to_dict('records'))
    if len(df_pivot) > 0:
        element = html.Div([
                dash_table.DataTable(
                df_pivot.to_dict('records'),[{"name": i.upper(), "id": i, "presentation": "markdown"} for i in display_columns],
                filter_action="native",
                filter_options={"case": "insensitive"},
                sort_action="native",
                is_focused=True,
                markdown_options={"html": True},
                page_size=8,
                style_cell={
                'padding': '10px',
                'font-size': '1.2em',
                'textAlign': 'center',
                'backgroundColor': '#ffffff',
                'border': '1px solid #ddd',
                },
                style_header={
                'backgroundColor': '#ffffff',
                'fontWeight': 'bold',
                'color': 'black',
                'border': '1px solid #ddd',
                },
                style_data={
                'height': 'auto',
                'overflowX': 'auto',
                },
                style_table={
                'overflowY': 'auto',
                'overflowX': 'auto',
                'border': '1px solid #ddd',
                'borderRadius': '5px',
                'boxShadow': '0 2px 5px rgba(0,0,0,0.1)',
                },
                style_data_conditional=[
                {
                    'if': {'row_index': 'odd'},
                    'backgroundColor': '#f7f7f7',
                },
                {
                    'if': {'column_id': 'SITE NAME'},
                    'textAlign': 'left !important',
                }
                ],
                id='status-tbl')
            ], className='table-container')
    else:
        element = html.Div(html.H3('No alarms for this site in the past day'), style={'textAlign': 'center'})

    return element, pd.merge(df_pivot, alarmCnt[['site', 'lat', 'lon']].drop_duplicates(subset='site', keep='first'), on='site', how='left')


def get_country_code(country_name):
    try:
        country = pycountry.countries.search_fuzzy(country_name)[0]
        return country.alpha_2
    except LookupError:
        return ''


def total_number_of_alarms(sitesDf):
    metaDf = pq.readFile('parquet/raw/metaDf.parquet')
    sitesDf = pd.merge(sitesDf, metaDf[['lat', 'lon', 'country']], on=['lat', 'lon'], how='left').drop_duplicates()
    site_totals = sitesDf.groupby('site')[['Infrastructure', 'Network', 'Other']].sum()

    highest_site = site_totals.sum(axis=1).idxmax()
    highest_site_alarms = site_totals.sum(axis=1).max()
    
    country_totals = sitesDf.groupby('country')[['Infrastructure', 'Network', 'Other']].sum()
    highest_country = country_totals.sum(axis=1).idxmax()
    highest_country_alarms = country_totals.sum(axis=1).max()
    
    status = {'critical': '🔴', 'warning': '🟡', 'ok': '🟢', 'unknown':'⚪'}
    status_count = sitesDf[['Status', 'site']].groupby('Status').count().to_dict()['site']
    for s, icon in status.items():
        if icon not in status_count:
            status_count[icon] = 0

    html_elements = [dbc.Col([
            dbc.Row(
                    html.H1('Status of all sites in the past 48 hours', 
                            className='card-title align-items-stretch'),
                align="center", className='w-100 p-2', style={"text-align": "center"}
            ),
            dbc.Row(children=[
                *[dbc.Col(
                    dbc.Card(
                        dbc.CardBody(
                            [
                                html.H4(f'{icon}', className='card-title'),
                                html.H3(f'{s}', className='card-title'),
                                html.H3(f'{status_count[icon]}', className='card-text'),
                            ]
                        ),
                        className='mb-3',
                    ),
                    md=3, xs=3, xl=3, className='status-count-numbers'
                ) for s, icon in status.items()]
            ], className='w-100 status-box', align="center", justify='center', style={
        "background-color": "transparent",  # Make the card background transparent
        }),
        ], className='boxwithshadow g-0 mb-1')]


    # html_elements.append(dbc.Col([
    #     dbc.Row(children=total_status, justify="center", align="center", className='h-100')],
    #     className='status-box boxwithshadow col-md-auto', md=6, xs=12))

    # # add the total number of alarms to the html
    # for k,v in sitesDf.sum(numeric_only=True).to_dict().items():
    #     html_elements.append(dbc.Col([
    #         html.H3(f'Total number of {k} alarms', className='status-title'),
    #         html.H1(f'{v}', className='status-number'),
    #     ], className='status-box boxwithshadow', md=2, xs=3))

    # add the highest number of alarms based on site name to the html
    country_code = get_country_code(sitesDf[sitesDf['site']==highest_site]['country'].values[0])
    html_elements.append(
    dbc.Row([
        dbc.Col([
            dbc.Row([
                html.H3(f'Highest number of alarms from site', className='status-title'),
                html.H1(f' {highest_site} ({country_code}): {highest_site_alarms}', className='status-number')
            ], align="center", className='h-100'),
            ], className='status-box boxwithshadow mb-1', md=6, sm=12),
        dbc.Col([
            dbc.Row([
                html.H3(f'Highest number of alarms from country', className='status-title'),
                html.H1(f'{highest_country}: {highest_country_alarms}', className='status-number'),
            ], align="center", className='h-100'),
            ], className='status-box boxwithshadow mb-1', md=6, sm=12)
        ], className='g-0')
    )

    return html_elements


def createTable(df, id):
    return dash_table.DataTable(
            df.to_dict('records'),
            columns=[{"name": i, "id": i, "presentation": "markdown"} for i in df.columns],
                markdown_options={"html": True},
                style_cell={
                    'padding': '2px',
                    'font-size': '1.5em',
                    'textAlign': 'center',
                    'whiteSpace': 'pre-line',
                    },
                style_header={
                    'backgroundColor': 'white',
                    'fontWeight': 'bold'
                },
                style_data={
                    'height': 'auto',
                    'overflowX': 'auto',
                },
                style_table={
                    'overflowY': 'auto',
                    'overflowX': 'auto'
                },
            id=id)


def explainStatuses():

  # Infrastructure:
  # if 'firewall issue' or 'source cannot reach any' -> red
  # otherwise yellow

  # this way we can then have network like this:
  # if 'bandwidth decreased from multiple' -> red
  # elif 'path changed' -> yellow
  # elif Infrastructure = 'red' -> grey
  # else -> green

  categoryDf = qrs.getSubcategories()

  red_infrastructure = ['firewall issue', 'source cannot reach any', 'complete packet loss']

  status = [
  {
    'status category': 'Global',
      'resulted status': '🔴',
      'considered alarm types': '\n'.join(['bandwidth decreased from multiple']),
      'trigger': 'any type has > 0 alarms'
  },
  {
    'status category': 'Global',
      'resulted status': '🟡',
      'considered alarm types': '\n'.join(['path changed']),
      'trigger': 'any type has > 0 alarms'
  },
  {
    'status category': 'Global',
      'resulted status': '⚪',
      'considered alarm types': '\n'.join(['Infrastructure']),
      'trigger': 'Infrastructure status is 🔴'
  },
  {
    'status category': 'Global',
      'resulted status': '🟢',
      'considered alarm types': '',
      'trigger': 'otherwise'
  },
  {
    'status category': 'Infrastructure',
      'considered alarm types': ',\n'.join(red_infrastructure),
      'trigger': 'any type has > 0 alarms',
      'resulted status': '🔴',
  },
  {
    'status category': 'Infrastructure',
      'considered alarm types': ',\n'.join(list(set(categoryDf[categoryDf['category']=='Infrastructure']['event'].unique()) - set(red_infrastructure))),
      'trigger': 'any type has > 0 alarms',
      'resulted status': '🟡',
  }]

  status_explaned = pd.DataFrame(status)
  categoryDf = categoryDf.pivot_table(values='event', columns='category', aggfunc=lambda x: '\n \n'.join(x))

  return createTable(status_explaned, 'status_explaned'), createTable(categoryDf, 'categoryDf')


dash.register_page(__name__, path='/')

pq = Parquet()
alarmsInst = Alarms()


def layout(**other_unknown_query_strings):
    dateFrom, dateTo = hp.defaultTimeRange(1)
    now = hp.defaultTimeRange(days=2, datesOnly=True)
    alarmCnt = pq.readFile('parquet/alarmsGrouped.parquet')
    statusTable, sitesDf = generate_status_table(alarmCnt)
    print("Period:", dateFrom," - ", dateTo)
    print(f'Number of alarms: {len(alarmCnt)}')
    
    
    # adding stats calculations for hosts not found
    dt = datetime.now()
    hostsNotFoundAlarms, expected_received_stats, stats_date = get_hosts_not_found_stats_data(dt)

    total_number = total_number_of_alarms(sitesDf)
    return html.Div([
        dbc.Col([
            dbc.Row([
                # Top left column with the map and the stacked bar chart
                dbc.Col([
                        dbc.Col(dcc.Graph(figure=builMap(sitesDf), id='site-map',
                                    className='cls-site-map'),
                            className='boxwithshadow page-cont mb-1 g-0 p-2 column-margin',
                            xl=12, lg=12, style={"background-color": "#b9c4d4;", "padding-top": "3%"}
                            # ), className="align-content-start", align='start'),
                            ),        
                        dbc.Col(
                        dcc.Loading(
                            html.Div(id="alarms-stacked-bar"),
                            style={'height': '1rem'}, color='#00245A'
                        ),
                        className="boxwithshadow page-cont mb-1 p-2 align-content-around",),
                ], lg=6, md=12, className='d-flex flex-column', align='around'), # d-flex and flex-column make the columns the same size
                # end of top left column

                # Top right column with status table, status statistics, and the search fields
                dbc.Col([
                    dbc.Row(children=total_number, className="h-100"),
                    dbc.Row([
                        dbc.Col(
                            [
                                html.Div(children=statusTable, id='site-status', className='status-table-cls'),
                                html.Div(
                                    [
                                        dbc.Button(
                                            "How was the status determined?",
                                            id="how-status-collapse-button",
                                            className="mb-3",
                                            color="secondary",
                                            n_clicks=0,
                                        ),
                                        dbc.Modal(
                                            [
                                                dbc.ModalHeader(dbc.ModalTitle("How was the status determined?")),
                                                dbc.ModalBody(id="how-status-modal-body"),
                                                dbc.ModalFooter(
                                                    dbc.Button("Close", id="close-how-status-modal", className="ml-auto", n_clicks=0)
                                                ),
                                            ],
                                            id="how-status-modal",
                                            size="lg",
                                            is_open=False,
                                        ),
                                    ], className="how-status-div",
                                ),
                            ], className='page-cont mb-1 p-1', xl=12
                        )
                    ], className="boxwithshadow page-cont mb-1"),

                    # Bottom part with the three pie charts
                   dbc.Row([
                        dbc.Row([
                            dbc.Row([
                                dbc.Row([
                                    # Title for the section
                                    dbc.Col([
                                        html.H3(children=f'Expected Testing Data Availability (per host) in Elasticsearch [{stats_date.strftime("%d-%m-%Y")}]',
                                                className='stats-title'
                                            )
                                        ], width=10),
                                    # Button to switch to historical data
                                    dbc.Col([
                                        dcc.Store(id='historical-data-for-graph', data=get_data_for_histogram(dt)),
                                        dcc.Store(id='hosts-not-found-stats', data=expected_received_stats),
                                        dcc.Store(id='date', data=dt),
                                        dcc.Dropdown(
                                            id='data-over-time-dropdown',
                                            options=['all (pie charts)', 'all (histograms)'],
                                            value='all (pie charts)',
                                            placeholder="Test Type",
                                            multi=False  # Allow multiple selections
                                        )
                                        ], width=2, className="align-left")
                                    ], className="mt-2 ml-1"),
                                # adding the pie charts or histogram
                                html.Div(id='graph-placeholder'),                          
                            ]),
                        ], className="mt-2 ml-2"),
                    ], className='boxwithshadow page-cont mb-1 p-1 align-center')
                ], lg=6, sm=12, className='d-flex flex-column h-100 pl-1'),
                # End of top right column
                
            ], className='w-100 h-100 g-0'),

            # Bottom part with search field and the list of alarms
            dbc.Row([
                dbc.Row([
                    dbc.Row([
                        dbc.Col([
                            dbc.Row([
                                dbc.Col([
                                    html.H3([
                                        html.I(className="fas fa-search"),
                                        "Search the Networking Alarms"
                                    ], className="l-h-3"),
                                ], align="center", className="text-left rounded-border-1"
                                    , md=12, xl=6),
                                dbc.Col([
                                    dcc.DatePickerRange(
                                        id='date-picker-range',
                                        month_format='M-D-Y',
                                        min_date_allowed=date.today() - pd.Timedelta(days=30),
                                        initial_visible_month=now[0],
                                        start_date=now[0],
                                        end_date=now[1]
                                    )
                                ], md=12, xl=6, className="mb-1 text-right")
                            ], justify="around", align="center", className="flex-wrap"),
                            dbc.Row([
                                dbc.Col([
                                    dcc.Dropdown(multi=True, id='sites-dropdown', placeholder="Search for a site"),
                                ]),
                            ]),
                            html.Br(),
                            dbc.Row([
                                dbc.Col([
                                    dcc.Dropdown(multi=True, id='events-dropdown', placeholder="Search for an event type"),
                                ]),
                            ]),
                            html.Br(),
                            dbc.Row([
                                dbc.Col([
                                    dbc.Button("Search", id="search-button", color="secondary",
                                            className="mlr-2", style={"width": "100%", "font-size": "1.5em"})
                                ])
                            ]),
                        ], lg=12, md=12, className="p-1"),
                    ], className="w-100 site g-0", justify="center", align="center"),
                ], className='w-100 boxwithshadow page-cont row', align="center")
            ], className='w-100 h-100 g-0 pl-1 pb-2'),
                
            dbc.Row([
                dbc.Col([
                    html.H1(f"List of alarms", className="text-center"),
                    html.Hr(className="my-2"),
                    html.Br(),
                    dcc.Loading(
                        html.Div(id='results-table'),
                        style={'height': '0.5rem'}, color='#00245A')
                ], className="boxwithshadow page-cont p-2",),
            ], className="g-0"),    
        ]),
    ], className='')
    
@dash.callback(
    [
        Output("sites-dropdown", "options"),
        Output("events-dropdown", "options"),
        Output('alarms-stacked-bar', 'children'),
        Output('results-table', 'children'),
    ],
    [
        Input('search-button', 'n_clicks'),
        Input('date-picker-range', 'start_date'),
        Input('date-picker-range', 'end_date'),
        Input("sites-dropdown", "search_value"),
        Input("sites-dropdown", "value"),
        Input("events-dropdown", "search_value"),
        Input("events-dropdown", "value")
    ],
    State("sites-dropdown", "value"),
    State("events-dropdown", "value")
)
def update_output(n_clicks, start_date, end_date, sites, all, events, allevents, sitesState, eventsState):
    ctx = dash.callback_context

    if not ctx.triggered or ctx.triggered[0]['prop_id'].split('.')[0] == 'search-button':
        if start_date and end_date:
            start_date, end_date = [f'{start_date}T00:01:00.000Z', f'{end_date}T23:59:59.000Z']
        else: start_date, end_date = hp.defaultTimeRange(2)
        alarmsInst = Alarms()
        frames, pivotFrames = alarmsInst.loadData(start_date, end_date)

        scntdf = pd.DataFrame()
        for e, df in pivotFrames.items():
            if len(df) > 0:
                if e != 'unresolvable host': # the tag is hostname for unresolvable hosts
                    df = df[df['tag'] != ''].groupby('tag')[['id']].count().reset_index().rename(columns={'id': 'cnt', 'tag': 'site'})
                else: df = df[df['site'] != ''].groupby('site')[['id']].count().reset_index().rename(columns={'id': 'cnt'})
                
                if e != 'path changed between sites':
                    df['event'] = e
                    scntdf = pd.concat([scntdf, df])

        # sites
        graphData = scntdf
        if (sitesState is not None and len(sitesState) > 0):
            graphData = graphData[graphData['site'].isin(sitesState)]

        sites_dropdown_items = []
        for s in sorted(scntdf['site'].unique()):
            if s:
                sites_dropdown_items.append({"label": s.upper(), "value": s.upper()})

        # events
        if eventsState is not None and len(eventsState) > 0:
            graphData = graphData[graphData['event'].isin(eventsState)]

        events_dropdown_items = []
        for e in sorted(scntdf['event'].unique()):
            events_dropdown_items.append({"label": e, "value": e})


        bar_chart = create_bar_chart(graphData)

        dataTables = []
        events = list(pivotFrames.keys()) if not eventsState or events else eventsState

        for event in sorted(events):
            df = pivotFrames[event]
            if 'site' in df.columns:
                df = df[df['site'].isin(sitesState)] if sitesState is not None and len(sitesState) > 0 else df
            elif 'tag' in df.columns:
                df = df[df['tag'].isin(sitesState)] if sitesState is not None and len(sitesState) > 0 else df

            if len(df) > 0:
                dataTables.append(generate_tables(frames[event], df, event, alarmsInst))
        dataTables = html.Div(dataTables)


        return [sites_dropdown_items, events_dropdown_items, dcc.Graph(figure=bar_chart), dataTables]
    else:
        raise dash.exceptions.PreventUpdate 

@dash.callback(
    [
    Output("how-status-modal", "is_open"),
    Output("how-status-modal-body", "children"),
    ],
    [
        Input("how-status-collapse-button", "n_clicks"),
        Input("close-how-status-modal", "n_clicks"),
    ],
    [State("how-status-modal", "is_open")],
)
def toggle_modal(n1, n2, is_open):
    if n1 or n2:
        if not is_open:
            catTable, statusExplainedTable = explainStatuses()
            data = dbc.Row([
                dbc.Col(children=[
                    html.H3('Category & Alarm types', className='status-title'),
                    html.Div(statusExplainedTable, className='how-status-table')
                ], lg=12, md=12, sm=12, className='page-cont pr-1 how-status-cont'),
                dbc.Col(children=[
                    html.H3('Status color rules', className='status-title'),
                    html.Div(catTable, className='how-status-table')
                ], lg=12, md=12, sm=12, className='page-cont how-status-cont')
            ], className='pt-1')
            return not is_open, data
        return not is_open, dash.no_update
    return is_open, dash.no_update


def create_bar_chart(graphData):
    # Calculate the total counts for each event type
    # event_totals = graphData.groupby('event')['cnt'].transform('sum')
    # Calculate percentage for each site relative to the event total
    # graphData['percentage'] = (graphData['cnt'] / event_totals) * 100

    graphData['percentage'] = graphData.groupby(['site', 'event'])['cnt'].transform(lambda x: x / x.sum() * 100)

    # Create the bar chart using percentage as the y-axis
    fig = px.bar(
        graphData, 
        x='site', 
        y='percentage', 
        color='event', 
        labels={'percentage': 'Percentage (%)', 'site': '', 'event': 'Event Type'},
        barmode='stack',
        color_discrete_sequence=px.colors.qualitative.Prism
    )

    # Add custom tooltip with original counts
    fig.update_traces(
        hovertemplate="<br>".join([
            "<span style='font-size:15px'>Site: %{x}</span>",
            "<span style='font-size:15px'>Count: %{customdata[0]}</span>",
        ]),
        customdata=graphData[['cnt', 'event']].values
    )

    # Update layout parameters
    fig.update_layout(
        margin=dict(t=20, b=20, l=0, r=0),
        showlegend=True,
        legend_orientation='h',
        legend_title_text='Alarm Type',
        legend=dict(
            x=0,
            y=1.35,
            orientation="h",
            xanchor='left',
            yanchor='top',
            font=dict(
                size=10,
            ),
        ),
        height=600,
        plot_bgcolor='#fff',
        autosize=True,
        width=None,
        title={
            'y': 0.01,
            'x': 0.95,
            'xanchor': 'right',
            'yanchor': 'bottom'
        },
        xaxis=dict(
            # tickangle=-45,
            automargin=True
        ),
        modebar={
            "orientation": 'v',
        }
    )

    return fig


# '''Takes selected site from the dropdpwn and generates a Dash datatable'''
def generate_tables(frame, unpacked, event, alarmsInst):
    ids = unpacked['id'].values
    dfr = frame[frame.index.isin(ids)]
    dfr = alarmsInst.formatDfValues(dfr, event)
    if event == 'hosts not found':
        dfr.drop(columns=['alarm_button'], inplace=True)
    dfr.sort_values('to', ascending=False, inplace=True)
    print('Home page,', event, "Number of alarms:", len(dfr))
    try:
        element = html.Div([
                    html.Br(),
                    html.H3(event.upper()),
                    dash_table.DataTable(
                        data=dfr.to_dict('records'),
                        columns=[{"name": i, "id": i, "presentation": "markdown"} for i in dfr.columns],
                        markdown_options={"html": True},
                        id=f'search-tbl-{event}',
                        page_current=0,
                        page_size=10,
                        style_cell={
                            'padding': '2px',
                            'font-size': '13px',
                            'whiteSpace': 'pre-line'
                            },
                        style_header={
                            'backgroundColor': 'white',
                            'fontWeight': 'bold'
                        },
                        style_data={
                            'height': 'auto',
                            'lineHeight': '15px',
                            'overflowX': 'auto'
                        },
                        style_table={
                        'overflowY': 'auto',
                        'overflowX': 'auto'
                        },
                        filter_action="native",
                        filter_options={"case": "insensitive"},
                        sort_action="native",
                    ),
                ], className='single-table')
        return element
    except Exception as e:
        print('dash_table.DataTable expects each cell to contain a string, number, or boolean value', e)
        return html.Div()

def expected_hosts_PsConfig():
    """
    The function reads parquet file with updated every 24 \
    hours data from psConfig about expected hosts and tests \
    results in the Elasticsearch.
    """
    parquet_path = 'parquet/raw/psConfigData.parquet'
    try: 
        print("Reading the parquet file with psConfig data...")
        df = pq.readFile(parquet_path)
        expected_tests_types = {
                                "owd": len(df[df["owd"] == True]),
                                "trace": len(df[df["trace"] == True]),
                                "throughput": len(df[df["throughput"] == True])
                                }
        df = pd.DataFrame.from_dict(expected_tests_types, orient='index', columns=['Count'])
        df['date'] = time
        print(f"psConfigData from parquet file: {df}")
        return df
    except Exception as err:
        print(err)
        print(f"Problems with reading the file {parquet_path}")
        
def count_unique_not_found_hosts(df, category):
    """
    The function helps to count unique hosts among \
    different categories from the Alarms to count the general statistics \
    about perfSonar missing tests in Elasticsearch.
    """
    missing_hosts = df.groupby("site")["hosts_not_found"].apply(lambda x: set(
            host for d in x 
            if isinstance(d, dict) and isinstance(d.get(category), (list, set, np.ndarray))
            for host in (d[category].tolist() if isinstance(d[category], np.ndarray) else d[category])
        ))
    all_missing_hosts = set().union(*missing_hosts.dropna())
    # print(all_missing_hosts)
    return (
        len(all_missing_hosts)
    )

def get_hosts_not_found_stats_data(time):
    """
    This function extracts the hosts not found alarms\
    for the last available day and count statistics for \
    expected and missing tests and hosts.
    """
    dayBeforeYesterdayS = (time - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    dayBeforeYesterdayE = (time - timedelta(days=2)).replace(hour=23, minute=59, second=59, microsecond=0)
    alarmsInst = Alarms()
    alarms, pivotFrames = alarmsInst.loadData(dayBeforeYesterdayS.strftime('%Y-%m-%dT%H:%M:%S.000Z'), dayBeforeYesterdayE.strftime('%Y-%m-%dT%H:%M:%S.000Z'))
    alarmsWithNotFoundHosts, pivotFrame = alarms['hosts not found'], pivotFrames['hosts not found']
    tests_types_results = {'owd': None, 'throughput': None, 'trace': None}
    try: 
        expected_stats = expected_hosts_PsConfig().to_dict()['Count']
        all_missing_num = 0
        for key in tests_types_results.keys():
            missing_hosts = count_unique_not_found_hosts(alarmsWithNotFoundHosts, key)
            expected_hosts = expected_stats[key]
            tests_types_results[key] = (missing_hosts, expected_hosts)
            all_missing_num += missing_hosts
        if all_missing_num == 0:
            print("!!!!!!!!!!!!!!!!!!!!suspicious!!!!!!!!!!!!!!!!!!!!!!!!!")
            print("Check parquet file existence and data format.")
        return alarmsWithNotFoundHosts, tests_types_results, dayBeforeYesterdayS
    except Exception as err:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(err)
        print("Check parquet file existence and data format.")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return alarmsWithNotFoundHosts, tests_types_results, dayBeforeYesterdayS

def build_pie_chart(stats, test_type):
    """
    The function builds pie chart with general
    statistics about data availability in Elasticsearch.
    """
    #TODO: add inside the donut chart trend(has the percent of got data grown or vice verse)
    part, total = stats[test_type]
    percentage = (part / total) * 100

    labels = ['Not Found', 'Found']
    values = [part, total - part]

    fig = px.pie(
        names=labels,
        values=values,
        hole=0.4,
        color=labels,
        color_discrete_map={'Not Found': '#00245a', 'Found': '#69c4c4'} 
    )

    fig.update_layout(
        height=200,  # Height of the chart
        width=200,   # Width of the chart
        autosize=False,  # Disable autosizing to enforce custom dimensions
        margin=dict(l=20, r=20, t=20, b=20),
        title={
            'text': test_type.upper(),  
            'y': 0.95,  
            'x': 0.05,
            'xanchor': 'left',
            'yanchor': 'top',
            'font': {'size': 12, 'color': '#00245a'}  
        },
        showlegend=False,
        template='plotly_white',
        annotations=[
            {
                'text': f'{(100-percentage):.1f}%',
                'x': 0.5,
                'y': 0.5,
                'font_size': 15,
                'showarrow': False
            }
        ]
    )

    fig.update_traces(
        marker=dict(
            line=dict(color='#ffffff', width=2)  # Add a white border to the slices
        )
    )

    return fig

def build_histogram(dictionary):
    df = pd.DataFrame(dictionary).T.reset_index()
    df[['owd', 'throughput', 'trace']] = df[['owd', 'throughput', 'trace']] * -1
    
    df.rename(columns={"index": "date"}, inplace=True)

    # Normalize the data (percentage change from the first day)
    # df_normalized = df.copy()
    # for col in ["owd", "throughput", "trace"]:
    #     df_normalized[col] = df[col] - df[col].iloc[0]

    df_melted = df.melt(id_vars=['date'], var_name='group', value_name='host_count')


    # Create a Plotly line plot
    fig = px.line(
        df_melted,
        x='date',
        y='host_count',
        color='group',
        labels={'date': 'Date', 'host_count': 'Number of Hosts', 'group': 'Group'},
        line_shape='linear'
    )

    # Show the plot
    return fig


@dash.callback(
    [
        Output("graph-placeholder", "children"), 
        Output("data-over-time-dropdown", "value")
    ],
    [
        Input("data-over-time-dropdown", "options"),
        Input("data-over-time-dropdown", "value"),  
        Input("historical-data-for-graph", "data"),
        Input("hosts-not-found-stats", "data"),
        Input("date", "data"),
    ],
)
def update_hosts_not_found_graphs(options, selected, histData, pieData, dt):
    if selected == "all (pie charts)":
        
        # three pie charts
        graph = dbc.Row([
                    dbc.Row([
                        # OWD stats
                        dbc.Col([
                            dcc.Graph(
                                figure=build_pie_chart(pieData, 'owd'),  
                                id='owd-stats',
                                className='cls-owd-stats',
                                style={'height': '200px'} 
                            ),
                        ], width=4, className='mt-2'), 

                        # Throughput stats
                        dbc.Col([
                            dcc.Graph(
                                figure=build_pie_chart(pieData, 'throughput'), 
                                id='throughput-stats',
                                className='cls-throughput-stats',
                                style={'height': '200px'}  
                            ),
                        ], width=4, className='mt-2'),  

                        # Trace stats
                        dbc.Col([
                            dcc.Graph(
                                figure=build_pie_chart(pieData, 'trace'), 
                                id='trace-stats',
                                className='cls-trace-stats',
                                style={'height': '200px'} 
                            ),
                        ], width=4, className='mt-2')
                    ]),
                    # Colored dots and explanations
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                # First colored dot and explanation
                                html.Div([
                                    html.Span(style={
                                        'display': 'inline-block',
                                        'width': '10px',
                                        'height': '10px',
                                        'border-radius': '50%',
                                        'background-color': '#69c4c4',  # custom color
                                        'margin-right': '8px',
                                        'margin-left': '8px'
                                    }),
                                    html.Span("expected hosts found in the Elasticsearch", style={'font-size': '10px'})
                                ]),

                                # Second colored dot and explanation
                                html.Div([
                                    html.Span(style={
                                        'display': 'inline-block',
                                        'width': '10px',
                                        'height': '10px',
                                        'border-radius': '50%',
                                        'background-color': '#00245a', 
                                        'margin-right': '8px',
                                        'margin-left': '8px'
                                    }),
                                    html.Span("expected hosts NOT found in the Elasticsearch", style={'font-size': '10px'})
                                        ])
                                    ], style={'background-color': 'transparent'})
                        ], width=2, className='w-100 mb-1'), 
                    ])
                ])
        return graph, "all (pie charts)"
    
    else:
        # histogram 14 days data
        graph = dbc.Row([
                    dbc.Row([
                            dbc.Col([
                                dcc.Graph(
                                    figure=build_histogram(histData), 
                                    id='histogram-graph',
                                    style={'height': '400px'}
                                ),
                            ], width=12, className='mt-0') 
                        ]),
                    dbc.Row([
                        dbc.Col([
                            html.Div([
                                # black do explanation of histogram
                                html.Div([
                                    html.Span(style={
                                        'display': 'inline-block',
                                        'width': '10px',
                                        'height': '10px',
                                        'border-radius': '50%',
                                        'background-color': 'black',
                                        'margin-right': '5px',
                                        'margin-left': '5px'
                                    }),
                                    html.Span("number of missing hosts in the Elasticsearch (14 days)", style={'font-size': '12px'})
                                ]),
                            ], style={'background-color': 'transparent'})
                        ], width=2, className='w-100 mb-1'), 
                    ])
                    ])
    return graph, "all (pie histograms)"



def get_data_for_histogram(rn):
    """
    The function extracts historical data from last 14 days \
    about test data availability in Elasticsearch. The data \
    is further used for the histogram on the home page.
    """
    histDateFrom = (rn - timedelta(days=16)).replace(hour=0, minute=0, second=0, microsecond=0)
    histDateTo = (rn - timedelta(days=2)).replace(hour=23, minute=59, second=59, microsecond=0)
    histAlarms, histPivotFrames = alarmsInst.loadData(histDateFrom.strftime('%Y-%m-%dT%H:%M:%S.000Z'), histDateTo.strftime('%Y-%m-%dT%H:%M:%S.000Z'))
    histDf, histFrame = histAlarms['hosts not found'], histPivotFrames['hosts not found']
    histDf['from'] = pd.to_datetime(histDf['from'])
    histDf['date'] = histDf['from'].dt.date
    grouped = histDf.groupby('date')
    all_dates = dict()
    # Iterate through each day
    for date, group in grouped:
        all_hosts_not_found = {'owd': set(), 'throughput': set(), 'trace': set()}
        for hosts_dict in group['hosts_not_found']:
            if isinstance(hosts_dict, dict):
                for key, hosts_list in hosts_dict.items():
                    if hosts_list is not None:
                        all_hosts_not_found[key].update(hosts_list)
        
        all_dates[date.strftime("%d/%m/%Y")] = all_hosts_not_found
    all_dates = {key: {k: len(d) for k, d in dictionary.items()} for key, dictionary in all_dates.items()}
    return all_dates