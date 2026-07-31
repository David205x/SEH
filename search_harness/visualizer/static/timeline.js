(function () {
  "use strict";

  function createTimeline({ conversation, messageTemplate, expandedRoles }) {
    function render(run, options = {}) {
      const {
        missingMessage = "No AgentRun was recorded.",
        modelInputs = "all",
        showStepMarkers = true,
        showToolCalls = true,
      } = options;
      conversation.replaceChildren();
      if (!run || !Array.isArray(run.trace)) {
        appendMessage("error", "run failure", missingMessage);
        return;
      }

      let currentStep = null;
      let renderedInitialInput = false;
      const pendingOutputs = new Map();
      for (const event of run.trace) {
        if (showStepMarkers && event.step !== currentStep) {
          currentStep = event.step;
          appendStepMarker(currentStep);
        }
        const payload = event.payload ?? {};
        switch (event.event_type) {
          case "model_input":
            if (modelInputs === "initial") {
              if (!renderedInitialInput) {
                appendInitialMessages(payload.messages);
                renderedInitialInput = true;
              }
            } else {
              appendMessage(
                "context",
                `model input · step ${event.step}`,
                JSON.stringify(payload.messages ?? [], null, 2),
              );
            }
            break;
          case "model_output":
            appendNativeReasoning(payload.metadata);
            pendingOutputs.set(event.step, String(payload.raw_output ?? ""));
            break;
          case "parsed_output":
            appendParsedOutput(payload, pendingOutputs.get(event.step) ?? "");
            pendingOutputs.delete(event.step);
            break;
          case "final_answer_candidate":
            appendMessage(
              "assistant",
              "final answer candidate",
              payload.answer ?? "",
            );
            break;
          case "final_deferred":
            appendMessage(
              "hook",
              "final decision · deferred",
              payload.feedback ?? "",
            );
            break;
          case "tool_call":
            if (showToolCalls) {
              appendMessage(
                "tool",
                `tool call · ${payload.name ?? "unknown"}`,
                JSON.stringify(payload, null, 2),
              );
            }
            break;
          case "tool_result":
            appendMessage(
              "tool",
              `tool result · ${payload.name ?? "unknown"}`,
              payload.content ?? "",
            );
            break;
          case "tool_error":
            appendMessage("error", "tool error", payload.error ?? "");
            break;
          case "invalid_output":
            appendMessage("error", "invalid output", payload.error ?? "");
            break;
          case "invalid_output_feedback":
            appendMessage("error", "format feedback", payload.message ?? "");
            break;
          case "max_steps_reached":
            appendMessage("error", "max steps reached", JSON.stringify(payload, null, 2));
            break;
          case "hook_applied":
            appendHookEvent(payload);
            break;
          case "hook_error":
            appendMessage(
              "hook",
              `hook error · ${payload.hook_id ?? "unknown"} · ${payload.phase ?? "unknown"}`,
              payload.error ?? "",
            );
            break;
          case "hook_model_output":
            appendHookModelOutput(payload);
            break;
          case "hook_model_error":
            appendHookModelError(payload);
            break;
          default:
            break;
        }
      }
      for (const [step, rawOutput] of pendingOutputs) {
        if (rawOutput.trim()) {
          appendMessage("assistant", `assistant content · step ${step}`, rawOutput);
        }
      }
      if (!run.trace.length) {
        appendMessage("error", "trace", "No event trace was recorded for this run.");
      }
    }

    function appendParsedOutput(payload, rawOutput) {
      if (typeof payload.inband_thinking === "string" && payload.inband_thinking.trim()) {
        appendMessage("inband-thinking", "in-band thinking", payload.inband_thinking);
      }
      const actions = completeActionBlocks(rawOutput);
      if (actions.length) {
        appendMessage("assistant", `assistant action · ${payload.kind ?? "parsed"}`, actions.join("\n\n"));
      } else if (!payload.inband_thinking && rawOutput.trim()) {
        appendMessage("assistant", "assistant content", rawOutput);
      }
    }

    function appendNativeReasoning(metadata) {
      if (!metadata || typeof metadata !== "object") return;
      for (const key of ["reasoning_content", "reasoning", "thinking"]) {
        const content = metadata[key];
        if (typeof content === "string" && content.trim()) {
          appendMessage("native-thinking", `native thinking · ${key}`, content);
        }
      }
    }

    function appendInitialMessages(messages) {
      if (!Array.isArray(messages)) return;
      for (const message of messages) {
        if (typeof message?.role === "string" && typeof message?.content === "string") {
          appendMessage(message.role, message.role, message.content);
        }
      }
    }

    function appendHookEvent(payload) {
      const hookId = payload.hook_id ?? "unknown hook";
      const phase = payload.phase ?? "unknown phase";
      const changes = Array.isArray(payload.changes) ? payload.changes : [];
      for (const message of appendedStageMessages(changes)) {
        appendMessage(
          "hook",
          `hook · ${hookId} · ${phase} · injected ${message.role}`,
          message.content,
        );
      }
      appendMessage(
        "hook",
        `hook patch · ${hookId} · ${phase}`,
        changes.length ? JSON.stringify(changes, null, 2) : "No state changes.",
      );
    }

    function appendHookModelOutput(payload) {
      const label = hookModelLabel(payload);
      appendMessage(
        "context",
        `hook model input · ${label}`,
        JSON.stringify(payload.model_input ?? {}, null, 2),
      );
      const metadata = payload.metadata;
      if (metadata && typeof metadata === "object") {
        for (const key of ["reasoning_content", "reasoning", "thinking"]) {
          if (typeof metadata[key] === "string" && metadata[key].trim()) {
            appendMessage(
              "native-thinking",
              `hook model native thinking · ${label} · ${key}`,
              metadata[key],
            );
          }
        }
      }
      appendMessage("hook", `hook model output · ${label}`, payload.raw_output ?? "");
    }

    function appendHookModelError(payload) {
      const label = hookModelLabel(payload);
      appendMessage(
        "context",
        `hook model input · ${label}`,
        JSON.stringify(payload.model_input ?? {}, null, 2),
      );
      appendMessage(
        "error",
        `hook model error · ${label}`,
        `${payload.error_type ?? "Error"}: ${payload.error ?? "Unknown model error"}`,
      );
    }

    function appendMessage(role, label, content) {
      const message = messageTemplate.content.firstElementChild.cloneNode(true);
      message.classList.add(`role-${role}`);
      message.classList.toggle("collapsed", !expandedRoles.has(role));
      const meta = message.querySelector(".message-meta");
      const contentNode = message.querySelector(".message-content");
      meta.textContent = label;
      updateToggleTitle(message, meta);
      meta.addEventListener("click", () => {
        message.classList.toggle("collapsed");
        updateToggleTitle(message, meta);
      });
      if (["tool", "hook", "context"].includes(role)) {
        contentNode.classList.add("technical-content");
        contentNode.setAttribute("translate", "no");
      }
      contentNode.textContent = String(content);
      conversation.append(message);
    }

    function appendStepMarker(step) {
      const marker = document.createElement("div");
      marker.className = "step-marker";
      marker.dataset.stepAnchor = String(step);
      marker.textContent = `Step ${step}`;
      conversation.append(marker);
    }

    return { render, appendMessage };
  }

  function completeActionBlocks(rawOutput) {
    const pattern = /<(tool_call|final_answer)>[\s\S]*?<\/\1>/g;
    return String(rawOutput).match(pattern) ?? [];
  }

  function appendedStageMessages(changes) {
    const additions = [];
    for (const change of changes) {
      if (change?.key !== "stage.model_input") continue;
      const before = change.before?.messages;
      const after = change.after?.messages;
      if (!Array.isArray(before) || !Array.isArray(after) || after.length <= before.length) continue;
      const unchangedPrefix = before.every(
        (message, index) => JSON.stringify(message) === JSON.stringify(after[index]),
      );
      if (!unchangedPrefix) continue;
      for (const message of after.slice(before.length)) {
        if (typeof message?.role === "string" && typeof message?.content === "string") {
          additions.push(message);
        }
      }
    }
    return additions;
  }

  function hookModelLabel(payload) {
    return [
      payload.hook_id ?? "unknown hook",
      payload.phase ?? "unknown phase",
      payload.profile ?? "unknown profile",
      payload.purpose ?? "unspecified purpose",
    ].join(" · ");
  }

  function updateToggleTitle(message, meta) {
    meta.title = message.classList.contains("collapsed") ? "Expand block" : "Collapse block";
  }

  window.AgentTimeline = { create: createTimeline };
}());
