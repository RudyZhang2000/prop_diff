from flask import Flask, render_template, jsonify
import threading
from PlayerPropFetcher import fetch_prizepicks_props, fetch_underdog_props
from compare_props import compare_props

app = Flask(__name__)

_diffs = []
_status = 'idle'
_status_message = 'No data loaded. Click Refresh to start.'


def _sort_key(d):
    pp, ud = d['prizepicks_line'], d['underdog_line']
    avg = (pp + ud) / 2
    pct_diff = abs(pp - ud) / avg if avg != 0 else 0
    mult = d.get('ud_relevant_mult', 1.0)
    return -(pct_diff * mult ** 6)


def run_refresh():
    global _diffs, _status, _status_message
    _status = 'loading'
    _status_message = 'Fetching PrizePicks...'
    try:
        pp_props = fetch_prizepicks_props()
        _status_message = 'Fetching Underdog...'
        ud_props = fetch_underdog_props()
        _status_message = 'Comparing...'
        diffs = compare_props(pp_props, ud_props)
        for d in diffs:
            pp, ud = d['prizepicks_line'], d['underdog_line']
            avg = (pp + ud) / 2
            d['pct_diff'] = round(abs(pp - ud) / avg * 100, 1) if avg != 0 else 0
        diffs.sort(key=_sort_key)
        _diffs = diffs
        _status = 'done'
        _status_message = f'{len(diffs)} props found'
    except Exception as e:
        _status = 'error'
        _status_message = str(e)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/refresh', methods=['POST'])
def refresh():
    global _status
    if _status == 'loading':
        return jsonify({'status': 'already_loading'})
    t = threading.Thread(target=run_refresh)
    t.daemon = True
    t.start()
    return jsonify({'status': 'started'})


@app.route('/status')
def status():
    return jsonify({'status': _status, 'message': _status_message})


@app.route('/data')
def data():
    return jsonify(_diffs)


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
