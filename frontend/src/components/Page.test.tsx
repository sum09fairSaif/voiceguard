import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Columns, Page } from "./Page";

// The tablet layout (#227) is CSS only; what the code has to guarantee is the
// order: a phone shows the parts one after another, and screen readers read
// them in this order at every size.
describe("Page", () => {
  it("keeps the header, the left column, the right column and the footer in reading order", () => {
    render(
      <Page header={<p>logo</p>} footer={<p>tabs</p>}>
        <Columns aside={<h1>heading</h1>}>
          <p>form</p>
        </Columns>
      </Page>,
    );

    const parts = ["logo", "heading", "form", "tabs"].map((text) => screen.getByText(text));
    for (let i = 1; i < parts.length; i += 1) {
      expect(parts[i - 1].compareDocumentPosition(parts[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    expect(screen.getByRole("main")).toContainElement(parts[3]);
  });

  it("works without columns, a header or a footer", () => {
    render(
      <Page>
        <p>loading</p>
      </Page>,
    );

    expect(screen.getByRole("main")).toHaveTextContent("loading");
  });
});
