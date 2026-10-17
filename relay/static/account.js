const profileForm = document.getElementById("profile-form");
const rotationDialog = document.getElementById("rotation-dialog");
const openRotationButton = document.getElementById("open-rotation-dialog");
const confirmRotationButton = document.getElementById("confirm-rotation");

if (openRotationButton) {
    openRotationButton.addEventListener("click", () => {
        if (profileForm.reportValidity()) rotationDialog.showModal();
    });
}

if (profileForm?.hasAttribute("data-rotation-required")) {
    profileForm.addEventListener("submit", (event) => {
        if (document.getElementById("rotation-confirmed").value === "yes") return;
        event.preventDefault();
        if (profileForm.reportValidity()) rotationDialog.showModal();
    });
}

if (confirmRotationButton) {
    confirmRotationButton.addEventListener("click", () => {
        document.getElementById("rotation-confirmed").value = "yes";
        rotationDialog.close();
        profileForm.requestSubmit();
    });
}
