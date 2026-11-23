(() => {
    const detectBtn = document.getElementById("detectDeadlockBtn");
    const recoverBtn = document.getElementById("recoverDeadlockBtn");

    if (!detectBtn || !recoverBtn) return;

    const message = document.getElementById("deadlockMessage");
    const results = document.getElementById("deadlockResults");
    const policySelect = document.getElementById("deadlockPolicy");
    const historyRefreshBtn = document.getElementById("deadlockHistoryRefresh");

    let simulation = null;
    let recoveryShown = false;

    function setMessage(text, type = "") {
        if (!message) return;
        message.textContent = text;
        message.className = "deadlock-message";
        if (type) message.classList.add(`is-${type}`);
    }

    function setText(id, value) {
        const element = document.getElementById(id);
        if (!element) return;

        element.textContent =
            value === null || value === undefined || value === ""
                ? "—"
                : String(value);
    }

    function makeCard(className, title, lines) {
        const card = document.createElement("article");
        card.className = className;

        const heading = document.createElement("h4");
        heading.textContent = title;
        card.appendChild(heading);

        lines.forEach((line) => {
            const paragraph = document.createElement("p");
            paragraph.textContent = line;
            card.appendChild(paragraph);
        });

        return card;
    }

    function renderProcesses(containerId, processes = []) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.replaceChildren();

        if (!processes.length) {
            const empty = document.createElement("p");
            empty.textContent = "No tracked student processes to display.";
            container.appendChild(empty);
            return;
        }

        processes.forEach((process) => {
            const state = process.state || "IDLE";

            const stateClass = state.includes("DEADLOCK")
                ? "is-waiting"
                : state.includes("RUNNING")
                    ? "is-running"
                    : "is-waiting";

            const card = makeCard(
                `deadlock-process-card ${stateClass}`,
                process.pid,
                [
                    `State: ${state}`,
                    `Holds: ${process.holds.join(", ") || "None"}`,
                    `Waiting for: ${process.waiting_for || "Nothing"}`
                ]
            );

            container.appendChild(card);
        });
    }

    function renderResources(containerId, resources = []) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.replaceChildren();

        if (!resources.length) {
            const empty = document.createElement("p");
            empty.textContent = "No tracked resources found.";
            container.appendChild(empty);
            return;
        }

        resources.forEach((resource) => {
            const allocated = resource.owner_student_id !== null &&
                resource.owner_student_id !== undefined;

            const card = makeCard(
                `deadlock-resource-card ${allocated ? "is-allocated" : "is-free"}`,
                resource.label || `Resource ${resource.resource_id}`,
                [
                    `Resource ID: ${resource.resource_id}`,
                    `Owner: ${allocated
                        ? (resource.owner || `Student ${resource.owner_student_id}`)
                        : "FREE"}`
                ]
            );

            container.appendChild(card);
        });
    }

    function renderGraph(containerId, graph = {}) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.replaceChildren();

        const edges = Object.entries(graph).flatMap(([from, targets]) =>
            (targets || []).map((to) => `${from} → ${to}`)
        );

        if (!edges.length) {
            const empty = document.createElement("p");
            empty.className = "deadlock-no-edges";
            empty.textContent = "No waiting edges. No circular wait remains.";
            container.appendChild(empty);
            return;
        }

        edges.forEach((edge) => {
            const item = document.createElement("span");
            item.className = "deadlock-edge";
            item.textContent = edge;
            container.appendChild(item);
        });
    }

    // ---------------------------------------------------------------
    // Visual wait-for graph (SVG). Nodes sit on a circle; every wait is
    // an arrow from the waiting student to the student holding the item,
    // labelled with the item name. Edges that belong to the deadlock
    // cycle are drawn in red.
    // ---------------------------------------------------------------
    const SVG_NS = "http://www.w3.org/2000/svg";

    function svgEl(name, attributes = {}) {
        const element = document.createElementNS(SVG_NS, name);
        Object.entries(attributes).forEach(([key, value]) => {
            element.setAttribute(key, String(value));
        });
        return element;
    }

    function shorten(text, limit) {
        const value = String(text || "");
        return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
    }

    function renderGraphVisual(containerId, graph = {}, waits = [],
                               names = {}, cycle = []) {
        const container = document.getElementById(containerId);
        if (!container) return;

        container.replaceChildren();

        const nodeIds = new Set(Object.keys(graph));
        const edgeMap = new Map();

        waits.forEach((wait) => {
            if (wait.owner_student_id === null ||
                wait.owner_student_id === undefined) return;

            const from = String(wait.waiting_student_id);
            const to = String(wait.owner_student_id);
            if (from === to) return;

            nodeIds.add(from);
            nodeIds.add(to);

            const key = `${from}->${to}`;
            if (!edgeMap.has(key)) edgeMap.set(key, { from, to, items: [] });
            edgeMap.get(key).items.push(wait.resource_name);
        });

        const nodes = Array.from(nodeIds).sort((a, b) => Number(a) - Number(b));

        if (!nodes.length || !edgeMap.size) {
            return;
        }

        const cycleEdges = new Set();
        const cycleNodes = new Set();
        for (let i = 0; i + 1 < cycle.length; i += 1) {
            cycleEdges.add(`${cycle[i]}->${cycle[i + 1]}`);
            cycleNodes.add(String(cycle[i]));
        }

        const width = 560;
        const height = 360;
        const cx = width / 2;
        const cy = height / 2 - 6;
        const radius = Math.min(width, height) / 2 - 70;
        const nodeRadius = 26;

        const position = new Map();
        nodes.forEach((id, index) => {
            if (nodes.length === 1) {
                position.set(id, { x: cx, y: cy });
                return;
            }
            const angle = -Math.PI / 2 + (2 * Math.PI * index) / nodes.length;
            position.set(id, {
                x: cx + radius * Math.cos(angle),
                y: cy + radius * Math.sin(angle)
            });
        });

        const svg = svgEl("svg", {
            viewBox: `0 0 ${width} ${height}`,
            role: "img",
            "aria-label": "Wait-for graph"
        });

        const markerId = `arrow-${containerId}`;
        const cycleMarkerId = `arrow-cycle-${containerId}`;
        const defs = svgEl("defs");

        [[markerId, "#a45c5c"], [cycleMarkerId, "#e16a6a"]].forEach(
            ([id, color]) => {
                const marker = svgEl("marker", {
                    id,
                    viewBox: "0 0 10 10",
                    refX: 9,
                    refY: 5,
                    markerWidth: 7,
                    markerHeight: 7,
                    orient: "auto-start-reverse"
                });
                marker.appendChild(svgEl("path", {
                    d: "M 0 0 L 10 5 L 0 10 z",
                    fill: color
                }));
                defs.appendChild(marker);
            }
        );
        svg.appendChild(defs);

        edgeMap.forEach((edge, key) => {
            const a = position.get(edge.from);
            const b = position.get(edge.to);
            const inCycle = cycleEdges.has(key);
            const hasReverse = edgeMap.has(`${edge.to}->${edge.from}`);

            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const length = Math.hypot(dx, dy) || 1;
            const curve = hasReverse ? 38 : 0;

            // Control point offset perpendicular to the straight line.
            const control = {
                x: (a.x + b.x) / 2 + (-dy / length) * curve,
                y: (a.y + b.y) / 2 + (dx / length) * curve
            };

            const unit = (from, to) => {
                const ux = to.x - from.x;
                const uy = to.y - from.y;
                const len = Math.hypot(ux, uy) || 1;
                return { x: ux / len, y: uy / len };
            };

            const startDir = unit(a, control);
            const endDir = unit(b, control);
            const start = {
                x: a.x + startDir.x * nodeRadius,
                y: a.y + startDir.y * nodeRadius
            };
            const end = {
                x: b.x + endDir.x * (nodeRadius + 3),
                y: b.y + endDir.y * (nodeRadius + 3)
            };

            const color = inCycle ? "#e16a6a" : "#a45c5c";

            svg.appendChild(svgEl("path", {
                d: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`,
                fill: "none",
                stroke: color,
                "stroke-width": inCycle ? 3 : 2,
                "marker-end": `url(#${inCycle ? cycleMarkerId : markerId})`
            }));

            const label = svgEl("text", {
                x: 0.25 * start.x + 0.5 * control.x + 0.25 * end.x,
                y: 0.25 * start.y + 0.5 * control.y + 0.25 * end.y - 6,
                fill: inCycle ? "#ffbebe" : "#c2babc",
                "font-size": 11,
                "text-anchor": "middle"
            });
            label.textContent = shorten(edge.items.join(", "), 22);
            svg.appendChild(label);
        });

        nodes.forEach((id) => {
            const p = position.get(id);
            const inCycle = cycleNodes.has(id);

            svg.appendChild(svgEl("circle", {
                cx: p.x,
                cy: p.y,
                r: nodeRadius,
                fill: "#191617",
                stroke: inCycle ? "#e16a6a" : "#8c83ed",
                "stroke-width": inCycle ? 3 : 2
            }));

            const idText = svgEl("text", {
                x: p.x,
                y: p.y + 4,
                fill: "#f5f5f5",
                "font-size": 12,
                "font-weight": 700,
                "text-anchor": "middle"
            });
            idText.textContent = id;
            svg.appendChild(idText);

            const nameText = svgEl("text", {
                x: p.x,
                y: p.y + nodeRadius + 16,
                fill: "#c2babc",
                "font-size": 11,
                "text-anchor": "middle"
            });
            nameText.textContent = shorten(names[id] || `Student ${id}`, 16);
            svg.appendChild(nameText);
        });

        container.appendChild(svg);
    }

    // Build the process display from the actual graph, waits and allocations.
    function buildProcesses(graph = {}, resources = [], waits = []) {
        const ids = new Set();

        Object.entries(graph).forEach(([id, owners]) => {
            ids.add(String(id));
            (owners || []).forEach((owner) => ids.add(String(owner)));
        });

        resources.forEach((resource) => {
            if (resource.owner_student_id !== null &&
                resource.owner_student_id !== undefined) {
                ids.add(String(resource.owner_student_id));
            }
        });

        waits.forEach((wait) => {
            ids.add(String(wait.waiting_student_id));
            if (wait.owner_student_id !== null &&
                wait.owner_student_id !== undefined) {
                ids.add(String(wait.owner_student_id));
            }
        });

        const names = new Map();

        resources.forEach((resource) => {
            if (resource.owner_student_id !== null &&
                resource.owner_student_id !== undefined &&
                resource.owner) {
                names.set(String(resource.owner_student_id), resource.owner);
            }
        });

        waits.forEach((wait) => {
            if (wait.waiting_student) {
                names.set(
                    String(wait.waiting_student_id),
                    wait.waiting_student
                );
            }
        });

        return Array.from(ids).sort((a, b) => Number(a) - Number(b))
            .map((id) => {
                const holds = resources
                    .filter((resource) =>
                        String(resource.owner_student_id) === id
                    )
                    .map((resource) => resource.label);

                const waitingFor = waits
                    .filter((wait) =>
                        String(wait.waiting_student_id) === id
                    )
                    .map((wait) => wait.resource_name);

                const hasOutgoingEdges = (graph[id] || []).length > 0;

                return {
                    pid: `Student ${id}${names.has(id) ? ` — ${names.get(id)}` : ""}`,
                    state: hasOutgoingEdges
                        ? "WAITING"
                        : holds.length
                            ? "RUNNING"
                            : "IDLE",
                    holds,
                    waiting_for: waitingFor.join(", ")
                };
            });
    }

    function renderInitial(data) {
        const resources = data.initial_allocation || data.resources || [];
        const graph = data.wait_for_graph || {};
        const waits = data.waits || [];

        setText("deadlockSource", data.source_table ||
            "os_resources and os_resource_waits");

        setText(
            "deadlockStatus",
            data.deadlock_detected ? "DEADLOCK DETECTED" : "NO DEADLOCK"
        );

        setText("deadlockMethod", "Wait-for graph cycle detection");

        renderProcesses(
            "deadlockProcesses",
            buildProcesses(graph, resources, waits)
        );
        renderGraphVisual(
            "deadlockGraphVisual",
            graph,
            waits,
            data.student_names || {},
            data.cycle || []
        );
        renderGraph("deadlockGraph", graph);
        renderResources("deadlockResourcesBefore", resources);

        setText(
            "deadlockCycle",
            data.cycle && data.cycle.length
                ? `Circular wait: ${data.cycle.join(" → ")}`
                : "No cycle detected."
        );

        const panel = document.getElementById("deadlockRecoveryPanel");
        if (panel) panel.hidden = true;

        recoveryShown = false;
        recoverBtn.disabled = !data.deadlock_detected;
        recoverBtn.textContent = "Recover Deadlock";

        if (results) results.hidden = false;
    }

    function renderRecovery(data) {
        const panel = document.getElementById("deadlockRecoveryPanel");
        if (panel) panel.hidden = false;

        const recoveries = data.recoveries && data.recoveries.length
            ? data.recoveries
            : (data.recovery ? [data.recovery] : []);

        if (recoveries.length) {
            const summary = recoveries.map((recovery) => {
                const released = (recovery.released_resources || [])
                    .map((resource) => resource.resource_name);
                const cancelled = (recovery.cancelled_request_ids ||
                    [recovery.cancelled_request_id]).join(", ");
                const moved = recovery.reallocated_to_name
                    ? `; ${released.join(", ") || "item"} reallocated to ${recovery.reallocated_to_name}`
                    : "";

                return `Victim: ${recovery.victim_name || `Student ${recovery.victim_student_id}`} ` +
                    `(cancelled request #${cancelled}; loan ended for ${released.join(", ") || "None"}${moved})`;
            }).join(". ");

            setText(
                "deadlockRecoverySummary",
                `${summary}. The victim's waiting request was cancelled, ` +
                "its blocking loan was ended, and the item was given to the " +
                "student who was waiting for it; other records were not changed."
            );
        } else {
            setText(
                "deadlockRecoverySummary",
                data.message || "No recovery was required."
            );
        }

        if (data.policy_label) {
            setText(
                "deadlockMethod",
                `Victim abort + preemption + reallocation — policy: ${data.policy_label}`
            );
        }

        const resourcesAfter =
            data.resource_state_after_recovery || data.resources || [];

        const graphAfter = data.wait_for_graph_after_recovery || {};
        const waitsAfter = data.waits_after_recovery || [];
        const stillDeadlocked = Boolean(data.deadlock_remains_after_recovery);

        renderProcesses(
            "deadlockProcessesAfter",
            buildProcesses(graphAfter, resourcesAfter, waitsAfter)
        );
        renderResources("deadlockResourcesAfter", resourcesAfter);
        renderGraphVisual(
            "deadlockGraphAfterVisual",
            graphAfter,
            waitsAfter,
            data.student_names || {},
            []
        );
        renderGraph("deadlockGraphAfter", graphAfter);

        setText(
            "deadlockFinalStatus",
            data.deadlock_remains_after_recovery
                ? "Another deadlock remains. Run detection again."
                : "Recovery complete: no circular wait remains."
        );

        recoveryShown = !stillDeadlocked;
        recoverBtn.textContent = stillDeadlocked
            ? "Recover Deadlock"
            : "Recovery Complete";
        recoverBtn.disabled = !stillDeadlocked;

        setMessage(data.message || "Recovery result displayed.", "success");
    }

    // ---------------------------------------------------------------
    // Deadlock history log
    // ---------------------------------------------------------------
    function renderHistory(entries = []) {
        const container = document.getElementById("deadlockHistory");
        if (!container) return;

        container.replaceChildren();

        if (!entries.length) {
            const empty = document.createElement("p");
            empty.textContent = "No deadlock has been detected yet.";
            container.appendChild(empty);
            return;
        }

        entries.forEach((entry) => {
            const recovered = entry.event_type === "RECOVERED";
            const when = String(entry.created_at || "").slice(0, 16);

            const lines = [`Time: ${when || "—"}`];

            if (entry.cycle_text) lines.push(`Cycle: ${entry.cycle_text}`);

            if (recovered) {
                lines.push(
                    `Victim: ${entry.victim_name || `Student ${entry.victim_student_id}`}` +
                    ` (cancelled request #${entry.cancelled_request_ids || "—"})`
                );
                lines.push(
                    `Item ${entry.item_name || "—"} reallocated to ` +
                    `${entry.reallocated_to_name || "—"}` +
                    (entry.new_transaction_id
                        ? ` (transaction #${entry.new_transaction_id})`
                        : "")
                );
                lines.push(
                    `Policy: ${entry.policy_label || entry.policy || "—"}`
                );
            }

            if (entry.triggered_by) {
                lines.push(`Triggered by student ${entry.triggered_by}`);
            }

            container.appendChild(makeCard(
                `deadlock-process-card ${recovered ? "is-running" : "is-waiting"}`,
                `#${entry.history_id} — ${recovered ? "RECOVERED" : "DETECTED"}`,
                lines
            ));
        });
    }

    async function loadHistory() {
        const container = document.getElementById("deadlockHistory");
        if (!container) return;

        try {
            const data = await requestJson(
                "/api/student-dashboard/os-deadlock/history",
                { method: "GET" }
            );
            renderHistory(data.history || []);
        } catch (error) {
            container.replaceChildren();
            const failed = document.createElement("p");
            failed.textContent = "Could not load deadlock history.";
            container.appendChild(failed);
        }
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                Accept: "application/json",
                ...(options.body ? { "Content-Type": "application/json" } : {}),
                ...(options.headers || {})
            },
            credentials: "same-origin"
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || `Request failed (${response.status}).`);
        }

        return data;
    }

    detectBtn.addEventListener("click", async () => {
        detectBtn.disabled = true;
        recoverBtn.disabled = true;
        if (results) results.hidden = true;

        simulation = null;
        recoveryShown = false;
        setMessage("Checking resource ownership and waiting records…");

        try {
            const data = await requestJson(
                "/api/student-dashboard/os-deadlock",
                { method: "GET" }
            );

            simulation = data;
            renderInitial(data);

            if (data.deadlock_detected) {
                setMessage(
                    "Deadlock detected. Pick a victim policy, then click Recover Deadlock.",
                    "error"
                );
            } else {
                setMessage("No deadlock detected. No loan or request records were changed.", "success");
            }

            loadHistory();
        } catch (error) {
            setMessage(error.message || "Could not detect deadlock.", "error");
            if (results) results.hidden = true;
        } finally {
            detectBtn.disabled = false;
        }
    });

    recoverBtn.addEventListener("click", async () => {
        if (!simulation || !simulation.deadlock_detected || recoveryShown) return;

        recoverBtn.disabled = true;
        detectBtn.disabled = true;
        setMessage("Rechecking the current graph and recovering if a cycle remains…");

        try {
            // Recovery is a separate POST operation. The backend rechecks
            // the current database state before changing anything.
            const policy = policySelect ? policySelect.value : "fewest_held";
            const data = await requestJson(
                "/api/student-dashboard/os-deadlock/recover",
                { method: "POST", body: JSON.stringify({ policy }) }
            );

            renderRecovery(data);
            simulation = data.deadlock_remains_after_recovery
                ? { deadlock_detected: true }
                : null;

            loadHistory();
        } catch (error) {
            setMessage(error.message || "Could not recover deadlock.", "error");
            recoverBtn.disabled = false;
        } finally {
            detectBtn.disabled = false;
        }
    });

    if (historyRefreshBtn) {
        historyRefreshBtn.addEventListener("click", loadHistory);
    }

    loadHistory();
})();