import os

import dash_core_components as dcc
import dash_dangerously_set_inner_html
import dash_html_components as html
from dash import Dash
from dash.dependencies import Output, Input, Event
from flask import Flask
from twisted.logger import Logger

import nucypher
from nucypher.characters.base import Character
from nucypher.network.nodes import Learner


class NetworkStatusApp:
    COLUMNS = ['Icon', 'Checksum', 'Nickname', 'Timestamp', 'Last Seen', 'Fleet State']

    def __init__(self,
                 title: str,
                 flask_server: Flask,
                 route_url: str,
                 *args,
                 **kwargs) -> None:
        self.log = Logger(self.__class__.__name__)

        self.dash_app = Dash(name=__name__,
                             server=flask_server,
                             assets_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets'),
                             url_base_pathname=route_url,
                             suppress_callback_exceptions=True)
        self.dash_app.title = title

    @staticmethod
    def header(title) -> html.Div:
        return html.Div([
            html.Div([
                html.Div([
                    html.Img(src='/assets/nucypher_logo.png'),
                ], className='banner'),
                html.Div([
                    html.H1(title, className='app_name'),
                ], className='row'),
                html.Div(f'v{nucypher.__version__}', className='row')
            ]),
        ])

    @staticmethod
    def previous_states(learner: Learner) -> html.Div:
        states_dict = learner.known_nodes.abridged_states_dict()
        return html.Div([
            html.H2('Previous States'),
            html.Div([
                NetworkStatusApp.states_table(states_dict)
            ]),
            html.Hr(),
        ], className='row')

    @staticmethod
    def states_table(states_dict) -> html.Table:
        row = []
        for key in states_dict:
            # store previous states in reverse order
            row.insert(0, html.Td(NetworkStatusApp.state_detail(states_dict[key])))
        return html.Table([html.Tr(row, id='state-table', className='row')])

    @staticmethod
    def state_detail(state) -> html.Div:
        return html.Div([
            html.H5(state['nickname']),
            html.Div([
                html.Div([
                    state['symbol']
                ], className='single-symbol'),
                html.Span(state['updated'], className='small'),
            ], className='nucypher-nickname-icon', style={'border-colour': state['color_hex']})
        ])

    @staticmethod
    def known_nodes(learner: Learner) -> html.Div:
        nodes = list()

        nodes_dict = learner.known_nodes.abridged_nodes_dict()
        teacher_node = learner.current_teacher_node()
        teacher_index = None
        for checksum in nodes_dict:
            node_data = nodes_dict[checksum]
            if checksum == teacher_node.checksum_public_address:
                teacher_index = len(nodes)

            nodes.append(node_data)

        return html.Div([
            html.H2('Known Nodes'),
            html.Div([
                html.Div('* Current Teacher',
                         style={'backgroundColor': '#1E65F3', 'color': 'white'},
                         className='two columns'),
            ], className='row'),
            html.Br(),
            html.Div([
                NetworkStatusApp.nodes_table(nodes, teacher_index)
            ], className='row')
        ], className='row')

    @staticmethod
    def nodes_table(nodes, teacher_index) -> html.Table:
        rows = []

        for i in range(len(nodes)):
            row = []
            node_dict = nodes[i]
            for col in NetworkStatusApp.COLUMNS:
                # update this depending on which
                # columns you want to show links for
                # and what you want those links to be
                cell = None
                if col == 'Icon':
                    icon_details = node_dict['icon_details']
                    cell = html.Td(children=html.Div([
                        html.Span(f'{icon_details["first_symbol"]}',
                                  className='single-symbol',
                                  style={'color': icon_details['first_color']}),
                        html.Span(f'{icon_details["second_symbol"]}',
                                  className='single-symbol',
                                  style={'color': icon_details['second_color']})
                    ], className='symbols'))
                elif col == 'Checksum':
                    cell = html.Td(f'{node_dict["checksum_address"][:10]}...')
                elif col == 'Nickname':
                    cell = html.Td(html.A(node_dict['nickname'],
                                          href='https://{}/status'.format(node_dict['rest_url']),
                                          target='_blank'))
                elif col == 'Timestamp':
                    cell = html.Td(node_dict['timestamp'])
                elif col == 'Last Seen':
                    cell = html.Td(node_dict['last_seen'])
                elif col == 'Fleet State':
                    # render html value directly
                    cell = html.Td(children=html.Div([
                        dash_dangerously_set_inner_html.DangerouslySetInnerHTML(node_dict['fleet_state_icon'])
                    ]))

                if cell is not None:
                    row.append(cell)

            style_dict = {'overflowY': 'scroll'}
            if i == teacher_index:
                # highlight teacher
                style_dict['backgroundColor'] = '#1E65F3'
                style_dict['color'] = 'white'

            rows.append(html.Tr(row, style=style_dict, className='row'))
        return html.Table(
            # header
            [html.Tr([html.Th(col) for col in NetworkStatusApp.COLUMNS], className='row')] +
            rows,
            id='node-table')


class MoeStatusApp(NetworkStatusApp):
    """
    Status app for 'Moe' monitoring node.
    """

    def __init__(self,
                 moe: Learner,
                 title: str,
                 flask_server: Flask,
                 route_url: str,
                 *args,
                 **kwargs) -> None:
        NetworkStatusApp.__init__(self, title, flask_server, route_url, args, kwargs)

        self.dash_app.layout = html.Div([
            dcc.Location(id='url', refresh=False),
            html.Div(id='header'),
            html.Div(id='prev-states'),
            html.Div(id='known-nodes'),
            dcc.Interval(id='status-update', interval=1000, n_intervals=0),
        ])

        @self.dash_app.callback(Output('header', 'children'),
                                [Input('url', 'pathname')])
        def header(pathname):
            return NetworkStatusApp.header(title)

        @self.dash_app.callback(Output('prev-states', 'children'),
                                events=[Event('status-update', 'interval')])
        def state():
            return NetworkStatusApp.previous_states(moe)

        @self.dash_app.callback(Output('known-nodes', 'children'),
                                events=[Event('status-update', 'interval')])
        def known_nodes():
            return NetworkStatusApp.known_nodes(moe)


class UrsulaStatusApp(NetworkStatusApp):
    """
    Status app for Ursula node.
    """

    def __init__(self,
                 ursula: Character,
                 title: str,
                 flask_server: Flask,
                 route_url: str,
                 *args,
                 **kwargs) -> None:
        NetworkStatusApp.__init__(self, title, flask_server, route_url, args, kwargs)

        self.dash_app.layout = html.Div([
            dcc.Location(id='url', refresh=False),
            html.Div(id='header'),
            html.Div(id='ursula_info'),
            html.Div(id='prev-states'),
            html.Div(id='known-nodes'),
            dcc.Interval(id='status-update', interval=1000, n_intervals=0),
        ])

        @self.dash_app.callback(Output('header', 'children'),
                                [Input('url', 'pathname')])
        def header(pathname):
            return NetworkStatusApp.header(title)

        @self.dash_app.callback(Output('ursula_info', 'children'),
                                [Input('url', 'pathname')])
        def ursula_info(pathname):
            domains = ''
            for domain in ursula.learning_domains:
                domains += f'  {domain.decode("utf-8")}  '

            return html.Div([
                html.Div([
                    html.H4('Icon', className='one column'),
                    html.Div([
                        html.Span(f'{ursula.nickname_metadata[0][1]}', className='single-symbol'),
                        html.Span(f'{ursula.nickname_metadata[1][1]}', className='single-symbol'),
                    ], className='symbols three columns'),

                ], className='row'),
                html.Div([
                    html.H4('Domains', className='one column'),
                    html.H5(domains, className='eleven columns'),
                ], className='row')
            ], className='row')

        @self.dash_app.callback(Output('prev-states', 'children'),
                                events=[Event('status-update', 'interval')])
        def state():
            return NetworkStatusApp.previous_states(ursula)

        @self.dash_app.callback(Output('known-nodes', 'children'),
                                events=[Event('status-update', 'interval')])
        def known_nodes():
            return NetworkStatusApp.known_nodes(ursula)