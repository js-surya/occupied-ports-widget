/* Glance v0.8.7: refresh only marked port widgets through Glance's own origin. */
(() => {
    if (window.occupiedPortsLiveLoaded) return;
    window.occupiedPortsLiveLoaded = true;
    const selector = '.occupied-ports-live';
    const interval = 3000;
    const signatures = new WeakMap();
    let busy = false;

    function setupCollapse(widget, expanded) {
        const list = widget.querySelector('.ports-grid');
        if (!list) return;
        const limit = Number(list.dataset.collapseAfter || 16);
        if (limit < 0 || list.children.length <= limit) return;
        list.classList.toggle('container-expanded', expanded);
        Array.from(list.children).slice(limit).forEach(item => item.classList.add('collapsible-item'));
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'expand-toggle-button';
        const label = document.createTextNode('');
        const icon = document.createElement('span');
        icon.className = 'expand-toggle-button-icon';
        button.append(label, icon);
        const update = () => {
            label.nodeValue = expanded ? 'Show less' : 'Show more';
            button.setAttribute('aria-expanded', String(expanded));
            button.classList.toggle('container-expanded', expanded);
            list.classList.toggle('container-expanded', expanded);
        };
        button.addEventListener('click', () => { expanded = !expanded; update(); });
        update();
        list.after(button);
    }

    async function refresh() {
        if (busy || document.hidden || typeof pageData === 'undefined') return;
        const widgets = [...document.querySelectorAll(selector)];
        if (!widgets.length || !document.querySelector('#page.content-ready')) return;
        busy = true;
        try {
            const url = `${pageData.baseURL}/api/pages/${encodeURIComponent(pageData.slug)}/content/`;
            const response = await fetch(url, {
                cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(10000)
            });
            if (!response.ok || response.redirected) throw new Error('Refresh unavailable');
            const fresh = new DOMParser().parseFromString(await response.text(), 'text/html');
            const replacements = [...fresh.querySelectorAll(selector)];
            if (replacements.length !== widgets.length) throw new Error('Widget configuration changed');
            widgets.forEach((widget, index) => {
                const current = widget.querySelector('.widget-content');
                const next = replacements[index].querySelector('.widget-content');
                if (!current || !next) return;
                if (signatures.get(widget) !== next.innerHTML) {
                    const expanded = !!widget.querySelector('.ports-grid.container-expanded');
                    current.replaceChildren(...[...next.childNodes].map(node => document.importNode(node, true)));
                    setupCollapse(widget, expanded);
                    signatures.set(widget, next.innerHTML);
                }
                widget.removeAttribute('data-ports-stale');
                widget.querySelector('[data-ports-refresh-status]')?.remove();
            });
        } catch (_) {
            widgets.forEach(widget => {
                widget.setAttribute('data-ports-stale', 'true');
                if (widget.querySelector('[data-ports-refresh-status]')) return;
                const status = document.createElement('div');
                status.dataset.portsRefreshStatus = '';
                status.className = 'color-negative size-h6 margin-top-10';
                status.setAttribute('role', 'status');
                status.textContent = 'Live updates paused — retrying';
                widget.querySelector('.widget-content')?.append(status);
            });
        } finally {
            busy = false;
        }
    }
    // A recursive timer avoids overlapping requests when an upstream is slow.
    async function tick() {
        await refresh();
        window.setTimeout(tick, interval);
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    tick();
})();
