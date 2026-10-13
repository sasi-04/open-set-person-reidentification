import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./Button";
import { ConfirmDialog } from "./Dialog";
import { FileDrop } from "./FileDrop";
import { Field, TextInput } from "./Form";
import { InfoTip } from "./InfoTip";
import { Progress } from "./Progress";
import { Tabs } from "./Tabs";
import { imageFile } from "@/test/utils";

describe("Button", () => {
  it("is disabled and announced as busy while loading, so it cannot be double-submitted", async () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: /save/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });
});

describe("Field", () => {
  it("links the label, hint and error message to the input", () => {
    render(<Field label="Threshold" hint="Between 0 and 1" error="Must be between 0 and 1."><TextInput /></Field>);
    const input = screen.getByLabelText("Threshold");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/Between 0 and 1.*Must be between/);
    expect(screen.getByRole("alert")).toHaveTextContent("Must be between 0 and 1.");
  });
});

describe("ConfirmDialog", () => {
  function Harness({ onConfirm }: { onConfirm: () => void }) {
    const [open, setOpen] = useState(true);
    return <ConfirmDialog open={open} onOpenChange={setOpen} title="Delete subject-001?" confirmLabel="Delete identity" requirePhrase="subject-001" consequences="Images are deleted." onConfirm={onConfirm} />;
  }
  it("spells out the consequences and keeps the destructive button disabled until the phrase is typed", async () => {
    const onConfirm = vi.fn();
    render(<Harness onConfirm={onConfirm} />);
    const dialog = screen.getByRole("dialog", { name: /delete subject-001/i });
    expect(within(dialog).getByText(/cannot be undone/i)).toBeInTheDocument();
    const confirm = within(dialog).getByRole("button", { name: "Delete identity" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "subject-00");
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByRole("textbox"), "1");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledOnce();
  });
  it("closes with the Escape key (keyboard accessible)", async () => {
    render(<Harness onConfirm={() => {}} />);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Tabs", () => {
  it("supports arrow-key navigation and shows only the active panel", async () => {
    render(<Tabs tabs={[{ id: "a", label: "First", content: <p>panel A</p> }, { id: "b", label: "Second", content: <p>panel B</p> }]} />);
    expect(screen.getByRole("tab", { name: "First" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("panel A")).toBeInTheDocument();
    screen.getByRole("tab", { name: "First" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Second" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Second" })).toHaveFocus();
    expect(screen.getByText("panel B")).toBeInTheDocument();
    expect(screen.queryByText("panel A")).not.toBeInTheDocument();
  });
});

describe("FileDrop", () => {
  const limits = { maxBytes: 5000, extensions: [".png", ".jpg"] };
  it("passes valid images on and explains rejected ones", async () => {
    const onFiles = vi.fn();
    const { container } = render(<FileDrop onFiles={onFiles} limits={limits} multiple />);
    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    await userEvent.upload(input, [imageFile("ok.png", 100), imageFile("huge.png", 9000), new File(["x"], "notes.txt", { type: "text/plain" })], { applyAccept: false });
    expect(onFiles).toHaveBeenCalledWith([expect.objectContaining({ name: "ok.png" })]);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/huge\.png.*limit/);
    expect(alert).toHaveTextContent(/notes\.txt.*not a supported image type/);
  });
  it("has a real, keyboard-reachable Browse button", () => {
    render(<FileDrop onFiles={() => {}} limits={limits} />);
    expect(screen.getByRole("button", { name: /browse files/i })).toBeEnabled();
  });
});

describe("InfoTip and Progress", () => {
  it("reveals its explanation on click and hides it on Escape", async () => {
    render(<InfoTip label="About FAR">False accepts divided by strangers.</InfoTip>);
    const trigger = screen.getByRole("button", { name: "About FAR" });
    await userEvent.click(trigger);
    expect(screen.getByRole("tooltip")).toHaveTextContent("False accepts");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
  it("exposes real progress to assistive technology", () => {
    render(<Progress value={0.42} label="Embedding images" />);
    expect(screen.getByRole("progressbar", { name: "Embedding images" })).toHaveAttribute("aria-valuenow", "42");
  });
});
