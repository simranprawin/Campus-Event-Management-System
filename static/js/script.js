document.addEventListener("DOMContentLoaded", () => {
  const deleteForms = document.querySelectorAll(".delete-form");

  deleteForms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      const confirmed = confirm(
        "Are you sure you want to continue?"
      );

      if (!confirmed) {
        event.preventDefault();
      }
    });
  });

  const flashes = document.querySelectorAll(".flash");

  flashes.forEach((flash) => {
    setTimeout(() => {
      flash.style.opacity = "0";
      flash.style.transition = "opacity 0.5s ease";

      setTimeout(() => {
        flash.remove();
      }, 500);
    }, 4000);
  });

  const dateInput = document.getElementById("date");

  if (dateInput) {
    const today = new Date().toISOString().split("T")[0];
    dateInput.setAttribute("min", today);
  }
});