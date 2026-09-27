import React, { useState, useEffect } from 'react';
import { 
  FolderKanban, 
  Plus, 
  Trash2, 
  ListChecks, 
  Check, 
  Globe, 
  Layers,
  ArrowRight,
  Building2,
  Sliders,
  Sparkles,
  BookOpen
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, ProjectInstruction } from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { Skeleton } from '../components/skeletons/Skeleton';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { EmptyState } from '../components/ui/EmptyState';

interface ProjectsPageProps {
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (p: Project | null) => void;
  refreshProjects: () => void;
}

export const ProjectsPage: React.FC<ProjectsPageProps> = ({
  projects,
  activeProject,
  setActiveProject,
  refreshProjects
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [selectedProject, setSelectedProject] = useState<Project | null>(activeProject || projects[0] || null);
  const [instructions, setInstructions] = useState<ProjectInstruction[]>([]);
  const [newRule, setNewRule] = useState('');
  
  // Create Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [clientName, setClientName] = useState('');
  const [description, setDescription] = useState('');
  const [ruleInput, setRuleInput] = useState('');

  useEffect(() => {
    if (selectedProject) {
      loadInstructions(selectedProject.id);
    }
  }, [selectedProject]);

  const loadInstructions = async (projectId: string) => {
    try {
      const list = await apiClient.getProjectInstructions(projectId);
      setInstructions(list);
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !code.trim()) return;

    try {
      const initialRules = ruleInput.split('\n').map(r => r.trim()).filter(Boolean);
      const created = await apiClient.createProject({
        name,
        code: code.toUpperCase(),
        client_name: clientName,
        description,
        instructions: initialRules
      });
      setShowCreateModal(false);
      setName('');
      setCode('');
      setClientName('');
      setDescription('');
      setRuleInput('');
      refreshProjects();
      setSelectedProject(created);
      setActiveProject(created);
      toast.success(`Đã tạo dự án ${created.name} thành công`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err.message, 'Failed to create project');
    }
  };

  const handleAddInstruction = async () => {
    if (!selectedProject || !newRule.trim()) return;
    try {
      await apiClient.addProjectInstruction(selectedProject.id, newRule.trim());
      setNewRule('');
      loadInstructions(selectedProject.id);
      refreshProjects();
      toast.success('Đã thêm hướng dẫn dự án');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to add rule');
    }
  };

  const handleDeleteInstruction = async (id: string) => {
    if (!selectedProject) return;
    try {
      await apiClient.deleteProjectInstruction(selectedProject.id, id);
      loadInstructions(selectedProject.id);
      refreshProjects();
      toast.success('Đã xóa hướng dẫn dự án');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to delete rule');
    }
  };

  const handleDeleteProject = async (id: string) => {
    const ok = await confirm({
      title: 'Xóa dự án',
      message: 'Bạn có chắc chắn muốn xóa dự án này? Toàn bộ hướng dẫn, thuật ngữ và bộ nhớ dịch liên quan sẽ bị xóa vĩnh viễn.',
      isDestructive: true,
      confirmText: 'Xóa dự án'
    });
    if (!ok) return;

    try {
      await apiClient.deleteProject(id);
      refreshProjects();
      setSelectedProject(null);
      if (activeProject?.id === id) setActiveProject(null);
      toast.success('Đã xóa dự án thành công');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to delete project');
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-canvas p-6 space-y-5">
      {/* Top Header */}
      <PageHeader
        title="Project Workspaces"
        description="Configure project-specific translation behaviors, custom rules, client terminology, and domain glossaries."
        actions={
          <Button
            variant="primary"
            onClick={() => setShowCreateModal(true)}
          >
            <Plus className="w-4 h-4 mr-1.5" />
            New Project
          </Button>
        }
      />

      {/* Main Grid: Projects List + Selected Project Workspace */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 overflow-hidden min-h-0">
        {/* Project List */}
        <Card className="flex flex-col overflow-hidden p-0 border border-border-subtle bg-surface">
          <div className="p-4 border-b border-border-subtle flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              All Projects ({projects.length})
            </h3>
            <span className="text-[11px] text-text-muted">Active: {activeProject?.code || 'None'}</span>
          </div>

          <div className="p-3 space-y-2 flex-1 overflow-y-auto">
            {projects.length === 0 ? (
              <EmptyState
                icon={<FolderKanban className="w-8 h-8" />}
                title="No projects created"
                description="Create your first client workspace to configure custom rules and glossaries."
                action={
                  <Button variant="outline" size="sm" onClick={() => setShowCreateModal(true)}>
                    Create Project
                  </Button>
                }
              />
            ) : (
              projects.map((p) => {
                const isSelected = selectedProject?.id === p.id;
                const isActive = activeProject?.id === p.id;
                return (
                  <div
                    key={p.id}
                    onClick={() => setSelectedProject(p)}
                    className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-primary/60 bg-surface-elevated shadow-sm ring-1 ring-primary/20'
                        : 'border-border-subtle bg-surface/50 hover:bg-surface-hover hover:border-border'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-semibold text-text-primary truncate max-w-[170px]">
                        {p.name}
                      </span>
                      <Badge variant="neutral" size="sm" className="font-mono text-[10px]">
                        {p.code}
                      </Badge>
                    </div>

                    <div className="text-[11px] text-text-muted flex items-center gap-1.5 truncate">
                      <Building2 className="w-3 h-3 text-text-muted shrink-0" />
                      <span>{p.client_name || 'Standard Client'}</span>
                    </div>

                    <div className="flex items-center justify-between mt-3 pt-2.5 border-t border-border-subtle text-[11px] text-text-muted">
                      <span>{p.instructions_count} rules • {p.glossary_count} terms</span>
                      {isActive ? (
                        <Badge variant="success" size="sm" className="flex items-center gap-1">
                          <Check className="w-3 h-3" /> Active
                        </Badge>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setActiveProject(p);
                          }}
                          className="text-primary hover:underline text-[11px] font-medium"
                        >
                          Set Active
                        </button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Card>

        {/* Selected Project Details & Rule Management */}
        <Card className="lg:col-span-2 flex flex-col overflow-hidden p-0 border border-border-subtle bg-surface">
          {selectedProject ? (
            <div className="flex-1 flex flex-col overflow-hidden p-5 space-y-4">
              {/* Project Header */}
              <div className="flex items-start justify-between border-b border-border-subtle pb-4">
                <div>
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <h3 className="text-base font-semibold text-text-primary">{selectedProject.name}</h3>
                    <Badge variant="info" size="sm" className="font-mono text-[11px]">
                      {selectedProject.code}
                    </Badge>
                    {activeProject?.id === selectedProject.id ? (
                      <Badge variant="success" size="sm" className="flex items-center gap-1">
                        <Check className="w-3 h-3" /> Active in Translator
                      </Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setActiveProject(selectedProject)}
                      >
                        Make Active
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-text-secondary mt-1.5 max-w-2xl leading-relaxed">
                    {selectedProject.description || 'No description provided for this workspace.'}
                  </p>
                  <div className="flex items-center gap-4 text-xs text-text-muted mt-2.5">
                    <span>Client: <strong className="text-text-secondary">{selectedProject.client_name || 'N/A'}</strong></span>
                    <span>Default Style: <strong className="text-text-secondary">{selectedProject.default_style}</strong></span>
                  </div>
                </div>

                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDeleteProject(selectedProject.id)}
                  className="text-danger hover:bg-danger/10 hover:text-danger"
                  title="Delete Project Workspace"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>

              {/* Instructions Section */}
              <div className="flex-1 flex flex-col overflow-hidden space-y-3 min-h-0">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-text-secondary flex items-center gap-2">
                    <ListChecks className="w-4 h-4 text-primary" />
                    Mandatory Translation Instructions ({instructions.length})
                  </h4>
                  <span className="text-[11px] text-text-muted">
                    Injected into AI system prompt for this project
                  </span>
                </div>

                {/* Add Rule Input */}
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <Input
                      value={newRule}
                      onChange={(e) => setNewRule(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleAddInstruction(); }}
                      placeholder="e.g. Always translate 障害 as 'sự cố', never use 'lỗi'..."
                    />
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleAddInstruction}
                    disabled={!newRule.trim()}
                  >
                    Add Rule
                  </Button>
                </div>

                {/* Rule List */}
                <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                  {instructions.map((inst, index) => (
                    <div
                      key={inst.id}
                      className="p-3 rounded-lg border border-border-subtle bg-surface-elevated/40 hover:bg-surface-elevated/70 transition flex items-center justify-between text-xs text-text-primary"
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="font-mono text-text-muted text-[11px] w-6">#{index + 1}</span>
                        <span className="font-sans leading-relaxed">{inst.rule_text}</span>
                      </div>
                      <button
                        onClick={() => handleDeleteInstruction(inst.id)}
                        className="text-text-muted hover:text-danger p-1 transition-colors"
                        title="Delete Rule"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}

                  {instructions.length === 0 && (
                    <div className="text-xs text-text-muted text-center py-10 border border-dashed border-border-subtle rounded-lg">
                      No custom instructions added yet. Add project-specific terminology rules above.
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center">
              <EmptyState
                icon={<FolderKanban className="w-10 h-10" />}
                title="No project selected"
                description="Select an existing workspace from the list or create a new one."
              />
            </div>
          )}
        </Card>
      </div>

      {/* Create Project Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create New Project Workspace"
        description="Define a dedicated translation context, client parameters, and custom AI prompt instructions."
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleCreate}>
              Create Project
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreate} className="space-y-3.5 text-xs">
          <div>
            <label className="text-text-secondary font-medium block mb-1">Project Name *</label>
            <Input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. ABC Banking Core Migration"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1">Project Code (Unique Identifier) *</label>
            <Input
              required
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="e.g. ABC-BANK"
              className="font-mono uppercase"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1">Client Name</label>
            <Input
              value={clientName}
              onChange={(e) => setClientName(e.target.value)}
              placeholder="e.g. Japanese Financial Corp"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Overview of the system, tech stack, and scope..."
              className="w-full h-18 bg-surface-elevated border border-border-subtle rounded-lg px-3 py-2 text-text-primary text-xs focus:outline-none focus:border-primary resize-none placeholder-text-muted"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1">Initial Project Rules (one per line)</label>
            <textarea
              value={ruleInput}
              onChange={(e) => setRuleInput(e.target.value)}
              placeholder="e.g. Always use 'người dùng' instead of 'user'&#10;Do not translate endpoint names"
              className="w-full h-20 bg-surface-elevated border border-border-subtle rounded-lg px-3 py-2 text-text-primary text-[11px] font-mono focus:outline-none focus:border-primary resize-none placeholder-text-muted"
            />
          </div>
        </form>
      </Modal>
    </div>
  );
};
