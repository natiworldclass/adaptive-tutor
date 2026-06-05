export interface Message {
  id: string;
  sender: 'tutor' | 'student';
  text: string;
  language?: string;
  mode?: string;
  timestamp: string;
  isStreaming?: boolean;
}

export interface ReflectionLog {
  id: string;
  title: string;
  category: string;
  content: string;
  timestamp: string;
  type: 'reasoning' | 'realization' | 'journal';
  rating?: number;
}

export interface CurriculumNode {
  id: string;
  title: string;
  subtitle: string;
  status: 'mastered' | 'in-progress' | 'locked';
  masteryPercentage?: number;
  lastReview?: string;
  nextReview?: string;
  prerequisite?: string;
  details?: string;
}

export interface CohortTopic {
  id: string;
  rank: string;
  moduleTitle: string;
  topicTitle: string;
  difficultyScore: number;
  difficultyText: 'High' | 'Mid' | 'Low';
  avgTimeMinutes: number;
  confusionTrend: 'Spiking' | 'Stable' | 'Declining';
}

export interface Intervention {
  id: string;
  title: string;
  description: string;
  type: 'warning' | 'auto_fix';
  deployed: boolean;
}
