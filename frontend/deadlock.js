(() => {
    const detectBtn = document.getElementById("detectDeadlockBtn");
    const recoverBtn = document.getElementById("recoverDeadlockBtn");
    if (!detectBtn || !recoverBtn) return;

    const status = document.getElementById("deadlockStatus");
    const results = document.getElementById("deadlockResults");
    const participantsPanel = document.getElementById("deadlockParticipantsPanel");
    const recoveryPanel = document.getElementById("deadlockRecoveryPanel");

    let recoverable = false;

    function setStatus(text, type = "") {
        status.textContent = text;
        status.className = "deadlock-status";
        if (type) status.classList.add(`is-${type}`);
    }

    function setText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value || "";
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                Accept: "application/json",
                ...(options.body ? { "Content-Type": "application/json" } : {})
            },
            credentials: "same-origin"
        });
        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || `Request failed (${response.status}).`);
        }

        return data;
    }

    function renderParticipants(data) {
        const cycle = Array.isArray(data.cycle)
            ? data.cycle.map(String)
            : [];
        const participantIds = cycle.length > 1 &&
            cycle[0] === cycle[cycle.length - 1]
            ? cycle.slice(0, -1)
            : cycle;
        const uniqueIds = Array.from(new Set(participantIds));
        const names = data.student_names || {};
        const cycleNames = uniqueIds.map((id) => {
            const cycleIndex = cycle.indexOf(id);
            return names[id] ||
                (data.cycle_names && data.cycle_names[cycleIndex]) ||
                `Student ${id}`;
        });
        const orderedCycleNames = cycle.map((id, index) =>
            names[id] ||
            (data.cycle_names && data.cycle_names[index]) ||
            `Student ${id}`
        );

        setText("deadlockParticipants", cycleNames.join(", "));
        setText("deadlockCycle", orderedCycleNames.join(" → "));
    }

    function renderDetection(data) {
        const detected = Boolean(data.deadlock_detected);
        recoverable = detected;
        results.hidden = false;
        participantsPanel.hidden = !detected;
        recoveryPanel.hidden = true;
        recoverBtn.disabled = !detected;
        recoverBtn.textContent = "Recover deadlock";

        if (detected) {
            renderParticipants(data);
            setStatus("Deadlock detected", "error");
        } else {
            setStatus("No deadlock detected", "success");
        }
    }

    function renderRecovery(data) {
        const recoveries = Array.isArray(data.recoveries) && data.recoveries.length
            ? data.recoveries
            : (data.recovery ? [data.recovery] : []);
        const summary = recoveries.map((recovery) => {
            const victim = recovery.victim_name ||
                `Student ${recovery.victim_student_id}`;
            const items = (recovery.released_resources || [])
                .map((resource) => resource.resource_name)
                .filter(Boolean)
                .join(", ");
            const recipient = recovery.reallocated_to_name;

            return [
                `Victim: ${victim}`,
                items,
                recipient ? `→ ${recipient}` : ""
            ].filter(Boolean).join(" · ");
        }).join(" | ");

        setText("deadlockRecoverySummary", summary || data.message);
        recoveryPanel.hidden = false;

        const remains = Boolean(data.deadlock_remains_after_recovery);
        recoverable = remains;
        recoverBtn.disabled = !remains;
        recoverBtn.textContent = remains
            ? "Recover deadlock"
            : "Recovery complete";
        setStatus(
            remains ? "Deadlock remains" : "No deadlock remains",
            remains ? "error" : "success"
        );
    }

    detectBtn.addEventListener("click", async () => {
        detectBtn.disabled = true;
        recoverBtn.disabled = true;
        results.hidden = true;
        recoverable = false;
        setStatus("Checking…");

        try {
            const data = await requestJson(
                "/api/student-dashboard/os-deadlock",
                { method: "GET" }
            );
            renderDetection(data);
        } catch (error) {
            setStatus(error.message || "Could not detect deadlock.", "error");
        } finally {
            detectBtn.disabled = false;
        }
    });

    recoverBtn.addEventListener("click", async () => {
        if (!recoverable) return;

        recoverBtn.disabled = true;
        detectBtn.disabled = true;
        setStatus("Recovering…");

        try {
            const data = await requestJson(
                "/api/student-dashboard/os-deadlock/recover",
                {
                    method: "POST",
                    body: JSON.stringify({ policy: "fewest_held" })
                }
            );
            renderRecovery(data);
        } catch (error) {
            setStatus(error.message || "Could not recover deadlock.", "error");
            recoverBtn.disabled = !recoverable;
        } finally {
            detectBtn.disabled = false;
        }
    });
})();
