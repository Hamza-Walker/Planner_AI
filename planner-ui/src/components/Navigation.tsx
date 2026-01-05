'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Leaf, Calendar, BarChart3 } from 'lucide-react';

const navItems = [
  { href: '/', label: 'Dashboard', icon: Leaf },
  { href: '/calendar', label: 'Calendar', icon: Calendar },
  { href: '/carbon', label: 'Carbon', icon: BarChart3 },
];

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav className="bg-white border-b border-gray-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <span className="text-2xl mr-2">🌱</span>
            <span className="font-bold text-xl text-gray-900">Planner AI</span>
          </div>
          <div className="flex space-x-4">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`inline-flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                    isActive
                      ? 'bg-green-100 text-green-700'
                      : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                  }`}
                >
                  <Icon className="w-4 h-4 mr-2" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
