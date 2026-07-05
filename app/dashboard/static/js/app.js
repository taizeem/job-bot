/**
 * Job Bot Dashboard - Frontend JavaScript helper utilities.
 * 
 * Provides interactive features such as toast notifications, 
 * modal actions, and dynamic dashboard counters.
 */

document.addEventListener("DOMContentLoaded", () => {
    console.log("Job Bot Dashboard initialized successfully.");
    setupKanbanDrags();
});

/**
 * Setup Kanban board drag-and-drop stubs.
 */
function setupKanbanDrags() {
    const cards = document.querySelectorAll(".kanban-card");
    const columns = document.querySelectorAll(".kanban-col-cards");
    
    cards.forEach(card => {
        card.setAttribute("draggable", "true");
        card.addEventListener("dragstart", (e) => {
            e.dataTransfer.setData("text/plain", card.dataset.id || "");
            card.style.opacity = "0.5";
        });
        
        card.addEventListener("dragend", () => {
            card.style.opacity = "1";
        });
    });
    
    columns.forEach(col => {
        col.addEventListener("dragover", (e) => {
            e.preventDefault();
        });
        
        col.addEventListener("drop", (e) => {
            e.preventDefault();
            const cardId = e.dataTransfer.getData("text/plain");
            if (cardId) {
                const card = document.querySelector(`.kanban-card[data-id="${cardId}"]`);
                if (card) {
                    col.appendChild(card);
                    // Trigger status update call here if needed
                }
            }
        });
    });
}
