import dash_core_components as dcc
import dash_html_components as html
from dash.dependencies import Output, Input

from nucypher.characters.base import Character
from nucypher.network.monitor.base import NetworkStatusPage


class UrsulaStatusApp(NetworkStatusPage):
    """
    Status application for Ursula node.
    """

    def __init__(self, ursula: Character, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.dash_app.layout = html.Div([
            dcc.Location(id='url', refresh=False),

            html.Div([
                html.Img(src='./assets/nucypher_logo.png', className='banner'),
                html.Div(id='header'),
            ], id="controls"),

            html.Div([
                html.Div(id='ursula_info'),
                html.Div(id='domains'),
            ]),

            # States and Known Nodes Table
            html.Div([
                html.Div(id='prev-states'),
                html.Br(),
                html.Div(id='known-nodes'),
            ]),

            # use a periodic update interval (every 5s)
            dcc.Interval(id='status-update', interval=5000, n_intervals=0),
        ], id='main')

        @self.dash_app.callback(Output('header', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def header(pathname):
            return self.header()

        @self.dash_app.callback(Output('ursula_info', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def ursula_info(pathname):
            info = html.Div([
                html.Div([
                    html.H3(f'{ursula.nickname}'),
                    html.H6(f'({ursula.checksum_address})')
                ], className='row'),
                html.Div([
                    html.H4('Icon', className='two columns'),
                    html.Div([
                        html.Span(f'{ursula.nickname_metadata[0][1]}', className='single-symbol'),
                        html.Span(f'{ursula.nickname_metadata[1][1]}', className='single-symbol'),
                    ], className='symbols ten columns'),
                ], className='row')
            ], className='row')

            return info

        @self.dash_app.callback(Output('domains', 'children'),
                                [Input('url', 'pathname')])  # on page-load
        def domains(pathname):
            domains = ' | '.join(ursula.learning_domains)
            return html.Div([
                html.H4('Domains', className='two columns'),
                html.H5(domains, className='ten columns'),
            ], className='row')

        @self.dash_app.callback(Output('prev-states', 'children'),
                                [Input('status-update', 'n_intervals')])
        def state(n):
            """Simply update periodically"""
            previous_states = list(reversed(ursula.known_nodes.states.values()))[:5]  # only latest 5
            states_dict_list = []
            for previous_state in previous_states:
                states_dict_list.append(ursula.known_nodes.abridged_state_details(previous_state))
            return self.previous_states(states_dict_list)

        @self.dash_app.callback(Output('known-nodes', 'children'),
                                [Input('status-update', 'n_intervals')])
        def known_nodes(n):
            """Simply update periodically"""
            teacher = ursula.current_teacher_node()
            teacher_checksum = None
            if teacher:
                teacher_checksum = teacher.checksum_address
            return self.known_nodes(nodes_dict=ursula.known_nodes.abridged_nodes_dict(),
                                    registry=ursula.registry,
                                    teacher_checksum=teacher_checksum)