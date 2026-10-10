import { Component } from "react";

// Catches errors thrown while a page renders, so one broken page doesn't blank the whole app
export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    console.error("A page crashed:", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        <p className="font-semibold">This page ran into a problem.</p>
        <p className="mt-1">Your data is safe. Try reloading the page, or pick another page from the menu.</p>
        <button
          onClick={() => window.location.reload()}
          className="mt-4 rounded-lg bg-red-600 px-3 py-1.5 text-white hover:bg-red-700"
        >
          Reload page
        </button>
      </div>
    );
  }
}