// A person shown in a dropdown as "Chidi Okafor, Sales Manager (Sales)" instead of just a name,
// so two people with similar names, or someone's job, are never a guess.

interface PersonLike {
  first_name: string;
  last_name: string;
  position_id?: string | null;
}

interface PositionLike {
  id: string;
  title: string;
  department_id: string;
}

interface DepartmentLike {
  id: string;
  name: string;
}

export function personLabel(person: PersonLike, positions: PositionLike[], departments: DepartmentLike[]): string {
  const name = person.first_name + " " + person.last_name;

  const position = positions.find(function (p) {
    return p.id === person.position_id;
  });
  if (!position) {
    return name + ", no position yet";
  }

  const department = departments.find(function (d) {
    return d.id === position.department_id;
  });
  if (!department) {
    return name + ", " + position.title;
  }
  return name + ", " + position.title + " (" + department.name + ")";
}
