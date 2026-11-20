import { KeyRound } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { changeOwnPassword } from "../../api/auth";
import { useAuth } from "../../contexts/AuthContext";
import { parseApiError, type FieldErrors } from "../../utils/apiErrors";
import { Button } from "../common/Button";
import { Card } from "../common/Card";
import { Field, FormErrorSummary, inputClass } from "../common/Form";
import { useToast } from "../common/Toast";

type PasswordForm = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};

const emptyForm: PasswordForm = {
  current_password: "",
  new_password: "",
  confirm_password: "",
};

function validatePasswordForm(form: PasswordForm) {
  const fieldErrors: FieldErrors = {};
  const messages: string[] = [];
  const add = (field: keyof PasswordForm, message: string) => {
    fieldErrors[field] = message;
    messages.push(message);
  };

  if (!form.current_password) add("current_password", "Current password is required.");
  if (form.new_password.length < 8) {
    add("new_password", "New password must contain at least 8 characters.");
  } else if (
    !/[A-Z]/.test(form.new_password)
    || !/[a-z]/.test(form.new_password)
    || !/\d/.test(form.new_password)
    || !/[^A-Za-z0-9]/.test(form.new_password)
  ) {
    add(
      "new_password",
      "New password must include uppercase and lowercase letters, a number, and a special character.",
    );
  }
  if (!form.confirm_password) {
    add("confirm_password", "Confirm your new password.");
  } else if (form.new_password !== form.confirm_password) {
    add("confirm_password", "New password and confirmation do not match.");
  }
  if (form.current_password && form.current_password === form.new_password) {
    add("new_password", "New password must be different from the current password.");
  }

  return { fieldErrors, messages };
}

export function ChangePasswordForm({ forced = false }: { forced?: boolean }) {
  const [form, setForm] = useState<PasswordForm>(emptyForm);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [messages, setMessages] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const { logout } = useAuth();
  const { notify } = useToast();
  const navigate = useNavigate();

  function updateField(field: keyof PasswordForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setFieldErrors((current) => ({ ...current, [field]: "" }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const validation = validatePasswordForm(form);
    if (validation.messages.length) {
      setFieldErrors(validation.fieldErrors);
      setMessages(validation.messages);
      return;
    }

    setSaving(true);
    setFieldErrors({});
    setMessages([]);
    try {
      const response = await changeOwnPassword(form);
      notify(response.message, "success");
      logout();
      navigate("/employee/login", {
        replace: true,
        state: { passwordChanged: true },
      });
    } catch (error) {
      const parsed = parseApiError(error, {
        current_password: "Current password",
        new_password: "New password",
        confirm_password: "Password confirmation",
      });
      setFieldErrors(parsed.fieldErrors);
      setMessages(parsed.messages);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-md bg-ocean-50 text-ocean-700">
          <KeyRound className="h-6 w-6" />
        </div>
        <div>
          <h2 className="font-display text-xl font-bold text-ink">
            {forced ? "Create a private password" : "Change Password"}
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {forced
              ? "Your temporary password must be replaced before you can continue."
              : "Use a strong password that you do not use for another account."}
          </p>
        </div>
      </div>

      <form className="mt-6 space-y-4" onSubmit={submit}>
        <FormErrorSummary messages={messages} />
        <Field label="Current password" required error={fieldErrors.current_password}>
          <input
            className={inputClass}
            type="password"
            autoComplete="current-password"
            value={form.current_password}
            onChange={(event) => updateField("current_password", event.target.value)}
          />
        </Field>
        <Field
          label="New password"
          required
          error={fieldErrors.new_password}
          hint="At least 8 characters with uppercase, lowercase, number, and special character."
        >
          <input
            className={inputClass}
            type="password"
            autoComplete="new-password"
            value={form.new_password}
            onChange={(event) => updateField("new_password", event.target.value)}
          />
        </Field>
        <Field label="Confirm new password" required error={fieldErrors.confirm_password}>
          <input
            className={inputClass}
            type="password"
            autoComplete="new-password"
            value={form.confirm_password}
            onChange={(event) => updateField("confirm_password", event.target.value)}
          />
        </Field>
        <Button type="submit" loading={saving} loadingLabel="Changing password..." className="w-full sm:w-auto">
          Change password
        </Button>
      </form>
    </Card>
  );
}
