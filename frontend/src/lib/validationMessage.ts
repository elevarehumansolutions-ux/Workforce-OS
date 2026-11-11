// Turns the server's "Validation failed" answer into sentences a person can act on.
// The server sends one entry per bad field: { field: "work_email", message: "value is not a valid email address: ..." }.

// Field names the server uses, in the words a person sees on the screen.
const FIELD_LABELS: Record<string, string> = {
  work_email: "Work email",
  email: "Email",
  first_name: "First name",
  last_name: "Last name",
  full_name: "Full name",
  password: "Password",
  phone: "Phone",
  title: "Title",
  name: "Name",
  weight: "Weight",
  target_value: "Target",
};

// The server's reasons come straight from the validation library ("Field required",
// "value is not a valid email address: An email address must have an @-sign.").
// The common ones get plain wording; anything else is shown as the server wrote it.
export function plainReason(message: string): string {
  const lower = message.toLowerCase();

  if (lower.includes("email address")) {
    return "Enter a valid email address, for example name@company.com.";
  }
  if (lower.includes("field required")) {
    return "This is required.";
  }
  if (lower.includes("at least 1 character")) {
    return "This cannot be empty.";
  }
  if (lower.includes("valid number") || lower.includes("valid integer") || lower.includes("valid decimal")) {
    return "Enter a number.";
  }

  // "Input should be greater than or equal to 1" -> "Must be 1 or more."
  const moreThan = message.match(/greater than or equal to ([0-9.]+)/i);
  if (moreThan) {
    return "Must be " + moreThan[1] + " or more.";
  }
  const lessThan = message.match(/less than or equal to ([0-9.]+)/i);
  if (lessThan) {
    return "Must be " + lessThan[1] + " or less.";
  }

  // Our own rules raised with ValueError arrive as "Value error, <our sentence>".
  return message.replace(/^value error,\s*/i, "");
}

// "work_email" -> "Work email" when the field is not in the table above.
export function labelForField(field: string): string {
  if (FIELD_LABELS[field]) {
    return FIELD_LABELS[field];
  }
  const words = field.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// One sentence per bad field, joined: "Work email: Enter a valid email address, ...".
// Returns an empty string when there is nothing to say, so the caller keeps its own message.
export function buildValidationMessage(details: { field: string; message: string }[]): string {
  const sentences: string[] = [];
  details.forEach(function (item) {
    sentences.push(labelForField(item.field) + ": " + plainReason(item.message));
  });
  return sentences.join(" ");
}
