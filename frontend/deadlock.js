(() => {
    const detectBtn = document.getElementById("detectDeadlockBtn");
    const recoverBtn = document.getElementById("recoverDeadlockBtn");

    // Do nothing if this script is loaded on another page.
    if (!detectBtn || !recoverBtn) return;

    const message = document.getElementById("deadlockMessage");
    const results = document.getElementById("deadlockResults");

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

    // Build the process display from the actual graph, waits and allocations.
    function buildProcesses(graph = {}, resources = [], waits = [])  {
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

    function renderRecovery(data)  {
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

    async function requestJson(url, options = {})  {
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
                    "Deadlock detected. Review the cycle, then click Recover Deadlock.",
                    "error"
                );
            } else {
                setMessage("No deadlock detected. No loan or request records were changed.", "success");
            }
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
            // the current database state before changing tracked resources.
            const data = await requestJson(
                "/api/student-dashboard/os-deadlock/recover",
                { method: "POST", body: JSON.stringify({}) }
            );

            renderRecovery(data);
            simulation = data.deadlock_remains_after_recovery
                ? { deadlock_detected: true }
                : null;
        } catch (error) {
            setMessage(error.message || "Could not recover deadlock.", "error");
            recoverBtn.disabled = false;
        } finally {
            detectBtn.disabled = false;
        }
    });
})();