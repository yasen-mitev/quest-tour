import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi, HttpErrorWithBody, type AuthSettings } from "../api";
import { SettingsScreen } from "./SettingsScreen";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  adminApi: {
    authSettings: vi.fn(),
    setEntraEnabled: vi.fn(),
    changePassword: vi.fn(),
    listAdmins: vi.fn(),
    createAdmin: vi.fn(),
    deleteAdmin: vi.fn(),
    resetAdminPassword: vi.fn(),
  },
}));

const GOOD_PASSWORD = "a-long-enough-password";

function settings(over: Partial<AuthSettings> = {}): AuthSettings {
  return {
    mode: "password",
    entra_configured: true,
    entra_enabled: false,
    session_provider: "password",
    email: "boss@example.com",
    ...over,
  };
}

describe("SettingsScreen", () => {
  beforeEach(() => {
    for (const fn of Object.values(adminApi)) vi.mocked(fn).mockReset();
    vi.mocked(adminApi.listAdmins).mockResolvedValue([
      { id: 1, email: "boss@example.com", is_bootstrap: true },
      { id: 2, email: "second@example.com", is_bootstrap: false },
    ]);
  });

  it("turns Microsoft Entra sign-in on", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.authSettings).mockResolvedValue(settings());
    vi.mocked(adminApi.setEntraEnabled).mockResolvedValue({ entra_enabled: true });
    render(<SettingsScreen />);
    const box = await screen.findByRole("checkbox", { name: "Microsoft Entra sign-in" });
    expect(box).not.toBeChecked();
    await user.click(box);
    expect(adminApi.setEntraEnabled).toHaveBeenCalledWith(true);
    await waitFor(() => expect(box).toBeChecked());
  });

  it("disables the toggle and explains why when Entra is not configured", async () => {
    vi.mocked(adminApi.authSettings).mockResolvedValue(settings({ entra_configured: false }));
    render(<SettingsScreen />);
    expect(await screen.findByRole("checkbox", { name: "Microsoft Entra sign-in" })).toBeDisabled();
    expect(screen.getByText(/ADMIN_ENTRA_\*/)).toBeInTheDocument();
  });

  it("disables the toggle in dev mode", async () => {
    vi.mocked(adminApi.authSettings).mockResolvedValue(settings({ mode: "dev" }));
    render(<SettingsScreen />);
    expect(await screen.findByRole("checkbox", { name: "Microsoft Entra sign-in" })).toBeDisabled();
  });

  it("shows the server's reason when the toggle is refused", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.authSettings).mockResolvedValue(settings({ entra_enabled: true }));
    vi.mocked(adminApi.setEntraEnabled).mockRejectedValue(
      new HttpErrorWithBody(409, { detail: "Cannot disable the last sign-in method" }),
    );
    render(<SettingsScreen />);
    const box = await screen.findByRole("checkbox", { name: "Microsoft Entra sign-in" });
    await user.click(box);
    expect(await screen.findByText("Cannot disable the last sign-in method")).toBeInTheDocument();
    expect(box).toBeChecked();
  });

  it("hides the password sections for an Entra session", async () => {
    vi.mocked(adminApi.authSettings).mockResolvedValue(settings({ session_provider: "entra" }));
    render(<SettingsScreen />);
    expect(await screen.findByText("Password admins are managed by a password admin.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Change my password" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Administrators" })).not.toBeInTheDocument();
    expect(adminApi.listAdmins).not.toHaveBeenCalled();
  });

  describe("change password", () => {
    async function fill(user: ReturnType<typeof userEvent.setup>, current: string, next: string, repeat: string) {
      await user.type(await screen.findByLabelText("Current password"), current);
      await user.type(screen.getByLabelText("New password"), next);
      await user.type(screen.getByLabelText("Repeat new password"), repeat);
      await user.click(screen.getByRole("button", { name: "Change password" }));
    }

    beforeEach(() => vi.mocked(adminApi.authSettings).mockResolvedValue(settings()));

    it("rejects a mismatched repeat without calling the API", async () => {
      const user = userEvent.setup();
      render(<SettingsScreen />);
      await fill(user, "old", GOOD_PASSWORD, GOOD_PASSWORD + "x");
      expect(await screen.findByText("The new passwords do not match.")).toBeInTheDocument();
      expect(adminApi.changePassword).not.toHaveBeenCalled();
    });

    it("rejects a short password without calling the API", async () => {
      const user = userEvent.setup();
      render(<SettingsScreen />);
      await fill(user, "old", "short", "short");
      expect(await screen.findByText("The new password must be at least 12 characters.")).toBeInTheDocument();
      expect(adminApi.changePassword).not.toHaveBeenCalled();
    });

    it("changes the password", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.changePassword).mockResolvedValue({ ok: true });
      render(<SettingsScreen />);
      await fill(user, "old-password", GOOD_PASSWORD, GOOD_PASSWORD);
      expect(adminApi.changePassword).toHaveBeenCalledWith("old-password", GOOD_PASSWORD);
      expect(await screen.findByRole("status")).toHaveTextContent(
        "Your password was changed. Other devices where you're signed in stay signed in.",
      );
    });

    it("says the current password is wrong on a 400", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.changePassword).mockRejectedValue(new HttpErrorWithBody(400, { detail: "bad" }));
      render(<SettingsScreen />);
      await fill(user, "old", GOOD_PASSWORD, GOOD_PASSWORD);
      expect(await screen.findByText("Current password is wrong")).toBeInTheDocument();
    });

    it("shows the first validation message on a 422", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.changePassword).mockRejectedValue(
        new HttpErrorWithBody(422, { errors: [{ field: "new_password", message: "Password is too common" }] }),
      );
      render(<SettingsScreen />);
      await fill(user, "old", GOOD_PASSWORD, GOOD_PASSWORD);
      expect(await screen.findByText("Password is too common")).toBeInTheDocument();
    });
  });

  describe("administrators", () => {
    beforeEach(() => vi.mocked(adminApi.authSettings).mockResolvedValue(settings()));

    it("lists the administrators", async () => {
      render(<SettingsScreen />);
      const list = await screen.findByRole("list", { name: "Administrators" });
      const rows = within(list).getAllByRole("listitem");
      expect(rows).toHaveLength(2);
      expect(rows[0]).toHaveTextContent("boss@example.com");
      expect(rows[1]).toHaveTextContent("second@example.com");
    });

    it("captions the first administrator and marks the signed-in admin as You, with Remove disabled", async () => {
      render(<SettingsScreen />);
      const list = await screen.findByRole("list", { name: "Administrators" });
      const [mine, other] = within(list).getAllByRole("listitem");
      expect(within(mine).getByText("First administrator · You")).toBeInTheDocument();
      expect(within(mine).getByRole("button", { name: "Reset password" })).toBeEnabled();
      // Kept but disabled, so the button columns line up; the reason is in a tooltip and for screen readers.
      const removeMine = within(mine).getByRole("button", { name: "Remove" });
      expect(removeMine).toBeDisabled();
      expect(removeMine).toHaveAttribute("title", "You cannot remove yourself");
      expect(removeMine).toHaveAccessibleDescription("You cannot remove yourself");
      expect(within(other).queryByText(/First administrator|You/)).not.toBeInTheDocument();
      expect(within(other).getByRole("button", { name: "Remove" })).toBeEnabled();
    });

    it("adds an administrator and refreshes the list", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.createAdmin).mockResolvedValue({ id: 3, email: "new@example.com", is_bootstrap: false });
      render(<SettingsScreen />);
      await user.type(await screen.findByLabelText("New admin email"), "new@example.com");
      await user.type(screen.getByLabelText("New admin password"), GOOD_PASSWORD);
      await user.click(screen.getByRole("button", { name: "Add administrator" }));
      expect(adminApi.createAdmin).toHaveBeenCalledWith("new@example.com", GOOD_PASSWORD);
      await waitFor(() => expect(adminApi.listAdmins).toHaveBeenCalledTimes(2));
    });

    it("removes an administrator only after confirmation", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.deleteAdmin).mockResolvedValue({ ok: true });
      render(<SettingsScreen />);
      const list = await screen.findByRole("list", { name: "Administrators" });
      await user.click(within(within(list).getAllByRole("listitem")[1]).getByRole("button", { name: "Remove" }));
      expect(adminApi.deleteAdmin).not.toHaveBeenCalled();
      await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }));
      expect(adminApi.deleteAdmin).toHaveBeenCalledWith(2);
      await waitFor(() => expect(adminApi.listAdmins).toHaveBeenCalledTimes(2));
    });

    it("shows the server's reason when a removal is refused", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.deleteAdmin).mockRejectedValue(
        new HttpErrorWithBody(409, { detail: "the last admin cannot be removed" }),
      );
      render(<SettingsScreen />);
      const list = await screen.findByRole("list", { name: "Administrators" });
      await user.click(within(within(list).getAllByRole("listitem")[1]).getByRole("button", { name: "Remove" }));
      await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }));
      expect(await screen.findByText("the last admin cannot be removed")).toBeInTheDocument();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    // Row 0 is boss@example.com (the signed-in admin), row 1 second@example.com.
    async function adminRow(index: number) {
      const list = await screen.findByRole("list", { name: "Administrators" });
      return within(list).getAllByRole("listitem")[index];
    }

    async function openResetDialog(user: ReturnType<typeof userEvent.setup>, index = 1) {
      const row = await adminRow(index);
      expect(within(row).queryByLabelText(/password/i)).not.toBeInTheDocument();
      await user.click(within(row).getByRole("button", { name: "Reset password" }));
      const email = index === 0 ? "boss@example.com" : "second@example.com";
      return screen.getByRole("dialog", { name: `Reset password for ${email}` });
    }

    async function resetPassword(user: ReturnType<typeof userEvent.setup>, index = 1) {
      const dialog = await openResetDialog(user, index);
      await user.type(within(dialog).getByLabelText("New password"), GOOD_PASSWORD);
      await user.type(within(dialog).getByLabelText("Repeat new password"), GOOD_PASSWORD + "{Enter}");
    }

    it("resets an administrator's password in a dialog", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.resetAdminPassword).mockResolvedValue({ ok: true });
      render(<SettingsScreen />);
      const dialog = await openResetDialog(user);
      expect(within(dialog).getByLabelText("New password")).toHaveFocus();
      await user.type(within(dialog).getByLabelText("New password"), GOOD_PASSWORD);
      await user.type(within(dialog).getByLabelText("Repeat new password"), GOOD_PASSWORD);
      await user.click(within(dialog).getByRole("button", { name: "Reset password" }));
      expect(adminApi.resetAdminPassword).toHaveBeenCalledWith(2, GOOD_PASSWORD);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      // Confirmed on the row that changed, with what to do next; nothing at the top of the section.
      expect(await within(await adminRow(1)).findByRole("status")).toHaveTextContent(
        "New password set. They aren't notified, so give it to them yourself.",
      );
      expect(within(await adminRow(0)).queryByRole("status")).not.toBeInTheDocument();
      expect(screen.queryByText(/Password reset for/)).not.toBeInTheDocument();
    });

    it("confirms a reset of your own password for the next sign-in", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.resetAdminPassword).mockResolvedValue({ ok: true });
      render(<SettingsScreen />);
      await resetPassword(user, 0);
      expect(adminApi.resetAdminPassword).toHaveBeenCalledWith(1, GOOD_PASSWORD);
      expect(await within(await adminRow(0)).findByRole("status")).toHaveTextContent(
        "New password set. Use it the next time you sign in.",
      );
    });

    it("clears the reset confirmation on the next action", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.resetAdminPassword).mockResolvedValue({ ok: true });
      render(<SettingsScreen />);
      await resetPassword(user);
      expect(await within(await adminRow(1)).findByRole("status")).toBeInTheDocument();
      await user.click(within(await adminRow(1)).getByRole("button", { name: "Remove" }));
      expect(within(await adminRow(1)).queryByRole("status")).not.toBeInTheDocument();
    });

    it("keeps the reset dialog open when the passwords differ or are too short", async () => {
      const user = userEvent.setup();
      render(<SettingsScreen />);
      const dialog = await openResetDialog(user);
      await user.type(within(dialog).getByLabelText("New password"), GOOD_PASSWORD);
      await user.type(within(dialog).getByLabelText("Repeat new password"), GOOD_PASSWORD + "x");
      await user.click(within(dialog).getByRole("button", { name: "Reset password" }));
      expect(within(dialog).getByText("The new passwords do not match.")).toBeInTheDocument();

      await user.clear(within(dialog).getByLabelText("New password"));
      await user.clear(within(dialog).getByLabelText("Repeat new password"));
      await user.type(within(dialog).getByLabelText("New password"), "short");
      await user.type(within(dialog).getByLabelText("Repeat new password"), "short{Enter}");
      expect(within(dialog).getByText("The new password must be at least 12 characters.")).toBeInTheDocument();
      expect(adminApi.resetAdminPassword).not.toHaveBeenCalled();
    });

    it("shows a refused reset inside the dialog", async () => {
      const user = userEvent.setup();
      vi.mocked(adminApi.resetAdminPassword).mockRejectedValue(new Error("network"));
      render(<SettingsScreen />);
      const dialog = await openResetDialog(user);
      await user.type(within(dialog).getByLabelText("New password"), GOOD_PASSWORD);
      await user.type(within(dialog).getByLabelText("Repeat new password"), GOOD_PASSWORD + "{Enter}");
      expect(await within(dialog).findByText("Could not reset the password.")).toBeInTheDocument();
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("closes the reset dialog on Cancel without calling the server", async () => {
      const user = userEvent.setup();
      render(<SettingsScreen />);
      const dialog = await openResetDialog(user);
      await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(adminApi.resetAdminPassword).not.toHaveBeenCalled();
    });
  });
});
