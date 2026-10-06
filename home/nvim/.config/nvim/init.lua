-- Minimal Neovim: sensible defaults, no plugins. Works with Neovim 0.7+.

vim.g.mapleader = " "

local opt = vim.opt
opt.number = true
opt.relativenumber = true
opt.mouse = "a"
opt.clipboard = "unnamedplus"
opt.undofile = true
opt.ignorecase = true
opt.smartcase = true
opt.expandtab = true
opt.shiftwidth = 4
opt.tabstop = 4
opt.smartindent = true
opt.wrap = false
opt.scrolloff = 8
opt.signcolumn = "yes"
opt.splitright = true
opt.splitbelow = true
opt.termguicolors = true
opt.updatetime = 250
opt.list = true
opt.listchars = { tab = "» ", trail = "·", nbsp = "␣" }

local map = vim.keymap.set
map("n", "<Esc>", "<cmd>nohlsearch<CR>")
map("n", "<leader>w", "<cmd>write<CR>", { desc = "Save" })
map("n", "<leader>q", "<cmd>quit<CR>", { desc = "Quit" })
map("n", "<leader>e", "<cmd>Explore<CR>", { desc = "File explorer" })
map("n", "<C-h>", "<C-w>h")
map("n", "<C-j>", "<C-w>j")
map("n", "<C-k>", "<C-w>k")
map("n", "<C-l>", "<C-w>l")
map("v", "J", ":m '>+1<CR>gv=gv", { desc = "Move selection down" })
map("v", "K", ":m '<-2<CR>gv=gv", { desc = "Move selection up" })
map("v", "<", "<gv")
map("v", ">", ">gv")

vim.api.nvim_create_autocmd("TextYankPost", {
  desc = "Briefly highlight yanked text",
  callback = function() vim.highlight.on_yank() end,
})

-- Two-space indent for languages that conventionally use it.
vim.api.nvim_create_autocmd("FileType", {
  pattern = { "lua", "yaml", "json", "javascript", "typescript", "html", "css", "terraform", "hcl" },
  callback = function() vim.opt_local.shiftwidth = 2; vim.opt_local.tabstop = 2 end,
})
