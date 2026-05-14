import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import subprocess
import sys

from main import run_pipeline


class InventoryOptimizerApp:

    def __init__(self, root):
        self.root = root
        self.root.title("Inventory Optimization System")
        self.root.resizable(False, False)
        self.root.configure(bg='#F4F6F9')

        self.file_path   = None
        self.output_path = None

        self._center_window(540, 580)
        self._build_ui()

    # ── center on screen ────────────────────────────────────────────────────

    def _center_window(self, w, h):
        self.root.geometry(f"{w}x{h}")
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ── build layout ────────────────────────────────────────────────────────

    def _build_ui(self):

        # ── title bar ──
        title_frame = tk.Frame(self.root, bg='#1F4E79', height=64)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)

        tk.Label(
            title_frame,
            text="Inventory Optimization System",
            bg='#1F4E79', fg='white',
            font=('Calibri', 15, 'bold')
        ).pack(expand=True)

        tk.Label(
            self.root,
            text="ML Demand Forecasting  +  MILP Inventory Optimization",
            bg='#F4F6F9', fg='#666666',
            font=('Calibri', 9, 'italic'),
            pady=4
        ).pack()

        self._divider()

        # ── step 1: file selection ──
        self._section_label("Step 1 — Select your inventory Excel file")

        file_inner = tk.Frame(self.root, bg='#F4F6F9')
        file_inner.pack(fill='x', padx=30, pady=(0, 12))

        self.file_label = tk.Label(
            file_inner,
            text="No file selected",
            bg='#FFFFFF',
            fg='#999999',
            font=('Calibri', 9),
            anchor='w',
            padx=10,
            pady=8,
            relief='flat',
            bd=1,
            width=52,
            wraplength=420
        )
        self.file_label.pack(side='left', fill='x', expand=True)

        tk.Button(
            file_inner,
            text="Browse",
            command=self._select_file,
            bg='#2E75B6', fg='white',
            font=('Calibri', 9, 'bold'),
            relief='flat', padx=14, pady=8,
            cursor='hand2', bd=0,
            activebackground='#1F5A9E',
            activeforeground='white'
        ).pack(side='left', padx=(8, 0))

        self._divider()

        # ── step 2: run ──
        self._section_label("Step 2 — Run the optimization")

        run_frame = tk.Frame(self.root, bg='#F4F6F9')
        run_frame.pack(fill='x', padx=30, pady=(0, 12))

        self.run_btn = tk.Button(
            run_frame,
            text="▶   Run Optimization",
            command=self._run,
            bg='#70AD47', fg='white',
            font=('Calibri', 11, 'bold'),
            relief='flat', padx=20, pady=10,
            state='disabled', cursor='hand2', bd=0,
            activebackground='#548235',
            activeforeground='white',
            width=30
        )
        self.run_btn.pack(anchor='w')

        self._divider()

        # ── status bar ──
        status_frame = tk.Frame(self.root, bg='#F4F6F9')
        status_frame.pack(fill='x', padx=30, pady=(8, 4))

        tk.Label(
            status_frame,
            text="STATUS",
            bg='#F4F6F9', fg='#888888',
            font=('Calibri', 8, 'bold'),
            anchor='w'
        ).pack(fill='x')

        self.status_var = tk.StringVar(value="Waiting for file selection...")
        self.status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg='#F4F6F9', fg='#444444',
            font=('Calibri', 9),
            anchor='w',
            wraplength=480
        )
        self.status_label.pack(fill='x')

        self._divider()

        # ── results panel (hidden until run completes) ──
        self.results_panel = tk.Frame(
            self.root, bg='#E8F4E8',
            relief='flat', bd=0
        )

        # Results panel inner content
        results_inner = tk.Frame(self.results_panel, bg='#E8F4E8')
        results_inner.pack(fill='both', expand=True, padx=20, pady=14)

        # Tick + heading
        heading_frame = tk.Frame(results_inner, bg='#E8F4E8')
        heading_frame.pack(fill='x', pady=(0, 8))

        tk.Label(
            heading_frame,
            text="✓",
            bg='#E8F4E8', fg='#375623',
            font=('Calibri', 18, 'bold')
        ).pack(side='left', padx=(0, 8))

        tk.Label(
            heading_frame,
            text="Optimization Complete",
            bg='#E8F4E8', fg='#375623',
            font=('Calibri', 13, 'bold')
        ).pack(side='left')

        # Summary numbers
        summary_frame = tk.Frame(results_inner, bg='#E8F4E8')
        summary_frame.pack(fill='x', pady=(0, 12))

        self.lbl_total = tk.Label(
            summary_frame,
            text="",
            bg='#E8F4E8', fg='#333333',
            font=('Calibri', 9),
            anchor='w'
        )
        self.lbl_total.pack(fill='x')

        self.lbl_reorder = tk.Label(
            summary_frame,
            text="",
            bg='#E8F4E8', fg='#C00000',
            font=('Calibri', 9, 'bold'),
            anchor='w'
        )
        self.lbl_reorder.pack(fill='x')

        self.lbl_sufficient = tk.Label(
            summary_frame,
            text="",
            bg='#E8F4E8', fg='#375623',
            font=('Calibri', 9),
            anchor='w'
        )
        self.lbl_sufficient.pack(fill='x')

        # Open report button — large and obvious
        self.open_btn = tk.Button(
            results_inner,
            text="📂   Open Reorder Report",
            command=self._open_report,
            bg='#1F4E79', fg='white',
            font=('Calibri', 11, 'bold'),
            relief='flat', padx=20, pady=10,
            cursor='hand2', bd=0,
            activebackground='#163A5F',
            activeforeground='white',
            width=30
        )
        self.open_btn.pack(anchor='w', pady=(4, 0))

        tk.Label(
            results_inner,
            text="Report is also saved in the output folder next to this application.",
            bg='#E8F4E8', fg='#666666',
            font=('Calibri', 8, 'italic'),
            anchor='w'
        ).pack(fill='x', pady=(6, 0))

    # ── helpers ─────────────────────────────────────────────────────────────

    def _divider(self):
        tk.Frame(self.root, bg='#DCDCDC', height=1).pack(
            fill='x', padx=0, pady=4
        )

    def _section_label(self, text):
        tk.Label(
            self.root,
            text=text,
            bg='#F4F6F9', fg='#1F4E79',
            font=('Calibri', 10, 'bold'),
            anchor='w',
            padx=30, pady=6
        ).pack(fill='x')

    # ── file selection ───────────────────────────────────────────────────────

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="Select Inventory Excel File",
            filetypes=[("Excel Files", "*.xlsx *.xls")]
        )
        if path:
            self.file_path = path
            filename = os.path.basename(path)
            self.file_label.config(text=f"  {filename}", fg='#1F4E79')
            self.run_btn.config(state='normal')
            self._set_status("File selected. Ready to run.", '#444444')
            # Hide results panel if visible from previous run
            self.results_panel.pack_forget()

    # ── run pipeline ─────────────────────────────────────────────────────────

    def _run(self):
        if not self.file_path:
            messagebox.showerror("Error", "Please select a file first.")
            return

        # Hide old results
        self.results_panel.pack_forget()

        self.run_btn.config(state='disabled')
        self._set_status("Starting...", '#444444')

        thread = threading.Thread(target=self._run_in_thread, daemon=True)
        thread.start()

    def _run_in_thread(self):
        try:
            output_path, summary = run_pipeline(
                self.file_path,
                progress_callback=lambda msg: self.root.after(
                    0, self._set_status, msg, '#444444'
                )
            )
            self.output_path = output_path
            self.root.after(0, self._on_success, summary)

        except Exception as e:
            self.root.after(0, self._on_error, str(e))

    # ── success ──────────────────────────────────────────────────────────────

    def _on_success(self, summary):
        self._set_status("Optimization complete.", '#375623')

        # Populate summary labels
        self.lbl_total.config(
            text=f"  Total products analyzed:          {summary['total']}"
        )
        self.lbl_reorder.config(
            text=f"  Products requiring reorder:       {summary['reorder']}"
        )
        self.lbl_sufficient.config(
            text=f"  Products with sufficient stock:   {summary['sufficient']}"
        )

        # Show results panel below the divider
        self.results_panel.pack(fill='x', padx=0, pady=0)

        self.run_btn.config(state='normal')

    # ── error ────────────────────────────────────────────────────────────────

    def _on_error(self, error_msg):
        self._set_status(f"Error: {error_msg}", '#C00000')
        self.run_btn.config(state='normal')
        messagebox.showerror("Error", error_msg)

    # ── open report ──────────────────────────────────────────────────────────

    def _open_report(self):
        if self.output_path and os.path.exists(self.output_path):
            if sys.platform == 'win32':
                os.startfile(self.output_path)
            elif sys.platform == 'darwin':
                subprocess.call(['open', self.output_path])
            else:
                subprocess.call(['xdg-open', self.output_path])
        else:
            messagebox.showerror(
                "Report Not Found",
                "The report file could not be found.\n"
                "Please run the optimization first."
            )

    # ── status helper ────────────────────────────────────────────────────────

    def _set_status(self, msg, color='#444444'):
        self.status_var.set(msg)
        self.status_label.config(fg=color)


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    root = tk.Tk()
    app = InventoryOptimizerApp(root)
    root.mainloop()