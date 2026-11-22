const borrowRequestBtn = document. getElementById("borrowRequestBtn");
const activityBtn = document.getElementById("activityBtn");
const refreshDashboardBtn = document. getElementById("refreshDashboardBtn");
const studentNotice = document.getElementById("studentNotice");
document.getElementById ("borrowDueDate").min = localDateString(new Date());
const dashboardPanels = [
    document.getElementById("borrowRequestPanel"),
    document.getElementById("activityPanel")
];
function  showNotice(message, isError = false) {
    studentNotice.textContent = message;
    studentNotice.classList.toggle("is-error", isError);
    studentNotice.hidden = false;
}
function  togglePanel(panel, button) {
    const shouldOpen = panel.hidden;
    dashboardPanels.forEach((item) => {
        item.hidden = true;
    });
    [borrowRequestBtn, activityBtn].forEach((item) => {
        item.setAttribute ("aria-expanded", "false");
    });
    if (shouldOpen) {
        panel.hidden = false;
        button.setAttribute("aria-expanded", "true");
        panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
}
async  function  apiRequest(url, options = {}) {
    const response = await fetch(url, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        }
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.message || "The request could not be completed.");
    }
    return data;
}
function  createItem(title, details, metadata) {
    const item = document.createElement("article");
    item.className = "student-item";
    const heading = document.createElement("h3");
    heading.textContent = title;
    item.appendChild(heading);
    if (details) {
        const description = document.createElement("p");
        description.textContent = details;
        item.appendChild(description);
    }
    const info = document.createElement("span");
    info.className = "student-item-meta";
    info.textContent = metadata;
    item.appendChild(info);
    return item;
}
function addReturnButton(item, request) {
    if (request.transaction_status !== "ACTIVE" || !request.transaction_id) {
        return;
    }
    const returnButton = document.createElement("button");
    returnButton.type = "button";
    returnButton.className = "student-item-action";
    returnButton.textContent = "Mark as returned";
    returnButton.addEventListener("click", async () => {
        returnButton.disabled = true;
        try {
            const result = await apiRequest(
                `/api/student-dashboard/transactions/${request.transaction_id}/return`,
                { method: "POST" }
            );
            showNotice(result.message);
            await loadDashboard();
        } catch (error) {
            showNotice(error.message, true);
            await loadDashboard();
        }
    });
    item.appendChild(returnButton);
}
function createDetailBox(label, value, sub, tone) {
    const box = document.createElement("div");
    box.className = `student-detail-box${tone ? ` is-${tone}` : ""}`;
    const labelText = document.createElement("span");
    labelText.className = "student-detail-label";
    labelText.textContent = label;
    const valueText = document.createElement("strong");
    valueText.className = "student-detail-value";
    valueText.textContent = value;
    const subText = document.createElement("span");
    subText.className = "student-detail-sub";
    subText.textContent = sub;
    box.appendChild(labelText);
    box.appendChild(valueText);
    box.appendChild(subText);
    return box;
}
function buildFeeBox(request) {
    const lateDays = Number(request.late_days) || 0;
    const lateFee = Number(request.late_fee) || 0;
    const active = request.transaction_status === "ACTIVE";
    if (lateDays > 0) {
        return createDetailBox(
            active ? "Late fee so far" : "Late fee",
            `Rs. ${lateFee}`,
            active
                ? `Overdue by ${lateDays} day(s)`
                : `Returned ${lateDays} day(s) late`,
            "late"
        );
    }
    return createDetailBox(
        "Late fee",
        "Rs. 0",
        active ? "Not overdue" : "No late fee",
        "ok"
    );
}
function buildReviewBox(request) {
    if (request.transaction_status !== "RETURNED") {
        return createDetailBox(
            "Review",
            "Pending",
            "Available after the item is returned",
            ""
        );
    }
    if (request.already_reviewed) {
        return createDetailBox(
            "Review",
            "Submitted",
            "Thanks for your feedback",
            "ok"
        );
    }
    const box = createDetailBox(
        "Review",
        "Not reviewed",
        "Rate the other student",
        ""
    );
    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "student-item-action";
    openButton.textContent = "Leave a review";
    openButton.addEventListener("click", () => {
        openButton.hidden = true;
        const form = document.createElement("div");
        form.className = "student-review-form";
        const rating = document.createElement("select");
        [5, 4, 3, 2, 1].forEach((value) => {
            const option = document.createElement("option");
            option.value = String(value);
            option.textContent = `${value} / 5`;
            rating.appendChild(option);
        });
        const comment = document.createElement("input");
        comment.type = "text";
        comment.maxLength = 500;
        comment.placeholder = "Comment (optional)";
        const submit = document.createElement("button");
        submit.type = "button";
        submit.className = "student-item-action";
        submit.textContent = "Submit review";
        submit.addEventListener("click", async () => {
            submit.disabled = true;
            try {
                const result = await apiRequest(
                    `/api/student-dashboard/transactions/${request.transaction_id}/review`,
                    {
                        method: "POST",
                        body: JSON.stringify({
                            rating: Number(rating.value),
                            comment: comment.value
                        })
                    }
                );
                showNotice(result.message);
            } catch (error) {
                showNotice(error.message, true);
            }
            await loadDashboard();
        });
        form.appendChild(rating);
        form.appendChild(comment);
        form.appendChild(submit);
        box.appendChild(form);
    });
    box.appendChild(openButton);
    return box;
}
function addLoanDetails(item, request) {
    if (!request.transaction_id) {
        return;
    }
    const details = document.createElement("div");
    details.className = "student-item-details";
    details.appendChild(buildFeeBox(request));
    details.appendChild(buildReviewBox(request));
    item.appendChild(details);
}
function renderEmpty(container, message) {
    const empty = document.createElement("p");
    empty.className = " student-empty";
    empty.textContent = message;
    container.replaceChildren (empty);
}
function  formatDate (value) {
    return value ? value.replace("T", " ").slice(0, 16) : "";
}
function  formatDueDate (value) {
    return value ? value.slice(0, 10) : "not set";
}
function  localDateString(date) {
    const  year = date.getFullYear();
    const  month = String(date.getMonth() + 1).padStart(2, "0");
    const  day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}
function  renderDashboard(data) {
    const ratingSummary = document.getElementById("myRatingSummary");
    if (ratingSummary && data.my_rating) {
        ratingSummary.textContent = data.my_rating.count
            ? `\u2605 Your rating: ${data.my_rating.average} / 5 from ${data.my_rating.count} review(s)`
            : "\u2605 You have no reviews yet";
    }
    const  board = document.getElementById("requestBoard");
    board.replaceChildren();
    if (!data.board_requests.length) {
        renderEmpty(board, "There are no open requests yet. Post one if you need something.");
    } else {
        data.board_requests.forEach((request) => {
            const isOwnRequest = request.student_id === data.student_id;
            const item = createItem(
                request.resource_name,
                request.description,
                `${request.category ? `${request.category} - ` : ""}Requested by ${request.requester_name}${isOwnRequest ? " (you)" : ""} - Due ${formatDueDate(request.due_date)} - ${formatDate(request.created_at)}`
            );
            if (!isOwnRequest) {
                const  acceptButton = document.createElement("button");
                acceptButton.type = "button";
                acceptButton.className = "student-item-action";
                acceptButton.textContent = "Offer to share";
                acceptButton.addEventListener("click", async () => {
                    acceptButton.disabled = true;
                    try {
                        const result = await apiRequest(
                            `/api/student-dashboard/requests/${request.request_id}/accept`,
                            { method: "POST" }
                        );
                        showNotice(result.message);
                        await loadDashboard();
                    } catch (error) {
                        showNotice(error.message, true);
                        await loadDashboard();
                    }
                });
                item.appendChild(acceptButton);
            }
            board.appendChild(item);
        });
    }
    const  myRequests = document.getElementById("myRequests");
    myRequests.replaceChildren();
    if (!data.requests.length) {
        renderEmpty(myRequests, "You have not posted any requests yet.");
    } else {
        data.requests.forEach((request) => {
            const item = createItem(
                request.resource_name,
                request.description,
                request.transaction_id
                    ? `Share confirmed with ${request.accepted_by_name || "another student"}${request.accepted_by_email ? ` (${request.accepted_by_email})` : ""} - Transaction #${request.transaction_id} ${request.transaction_status} - Due ${formatDueDate(request.transaction_due_date)}`
                    : request.request_status === "OFFERED"
                        ? `Share offer from ${request.accepted_by_name || "another student"} - Waiting for your confirmation - Due ${formatDueDate(request.due_date)}`
                        : request.request_status === "UNAVAILABLE"
                            ? "Another borrower confirmed this item first - No transaction was created for this request"
                        : `${request.request_status} - Due ${formatDueDate(request.due_date)} - ${formatDate(request.created_at)}`
            );
            if (request.request_status === "OFFERED") {
                const confirmButton = document.createElement("button");
                confirmButton.type = "button";
                confirmButton.className = "student-item-action";
                confirmButton.textContent = "Confirm share & create transaction";
                confirmButton.addEventListener("click", async () => {
                    confirmButton.disabled = true;
                    try {
                        const result = await apiRequest(
                            `/api/student-dashboard/requests/${request.request_id}/confirm-share`,
                            { method: "POST" }
                        );
                        showNotice(result.message);
                        await loadDashboard();
                    } catch (error) {
                        showNotice(error.message, true);
                        await loadDashboard();
                        confirmButton.disabled = false;
                    }
                });
                item.appendChild(confirmButton);
            }
            addLoanDetails(item, request);
            addReturnButton(item, request);
            myRequests.appendChild(item);
        });
    }
    const acceptedRequests = document.getElementById("acceptedRequests");
    acceptedRequests.replaceChildren();
    if (!data.accepted_requests.length) {
        renderEmpty(acceptedRequests, "You have not accepted any requests yet.");
    } else {
        data.accepted_requests.forEach((request) => {
            const acceptedItem = createItem(
                request.resource_name,
                request.description,
                request.transaction_id
                    ? `Transaction #${request.transaction_id} ${request.transaction_status} - Due ${formatDueDate(request.transaction_due_date)} - For ${request.requester_name}${request.requester_email ? ` (${request.requester_email})` : ""}`
                    : request.offer_status === "Unavailable"
                        ? "Another borrower confirmed this item first - This share offer was not selected"
                        : `Offer sent - Waiting for ${request.requester_name} to confirm - Expected return ${formatDueDate(request.due_date)}`
            );
            addLoanDetails(acceptedItem, request);
            addReturnButton(acceptedItem, request);
            acceptedRequests.appendChild(acceptedItem);
        });
    }
}
async function  loadDashboard() {
    refreshDashboardBtn.disabled = true;
    try {
        const data = await apiRequest("/api/student-dashboard");
        renderDashboard(data);
    } catch (error) {
        showNotice(error.message, true);
    } finally {
        refreshDashboardBtn.disabled = false;
    }
}
async function  submitRequest (form) {
    const values = Object.fromEntries(new FormData(form).entries());
    const submitButton = form.querySelector ('button[type="submit"]');
    submitButton.disabled = true;
    try {
        const result = await apiRequest("/api/student-dashboard/requests", {
            method: "POST",
            body: JSON.stringify(values)
        });
        showNotice (result.message);
        form.reset();
        form.closest(".student-panel").hidden = true;
        borrowRequestBtn.setAttribute("aria-expanded", "false");
        await loadDashboard();
    } catch (error) {
        showNotice(error.message, true);
    } finally {
        submitButton.disabled = false;
    }
}
borrowRequestBtn.addEventListener("click", () => {
    togglePanel(document.getElementById("borrowRequestPanel"), borrowRequestBtn);
});
activityBtn.addEventListener("click", () => {
    togglePanel(document.getElementById("activityPanel"), activityBtn);
});
refreshDashboardBtn.addEventListener("click", loadDashboard);
document.querySelectorAll("[data-close-panel]").forEach((button) => {
    button.addEventListener("click", () => {
        button .closest(".student-panel").hidden = true;
        [borrowRequestBtn, activityBtn].forEach((item) => {
            item.setAttribute ("aria-expanded", "false");
        });
    });
});
document.getElementById ("borrowRequestForm").addEventListener("submit", (event) => {
    event.preventDefault();
    submitRequest(event.currentTarget);
});
loadDashboard();